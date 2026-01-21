# admin/routes.py
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import asyncio
from decimal import Decimal
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status, UploadFile, File, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from jose import JWTError, jwt
from beanie import Document, PydanticObjectId
from pydantic import BaseModel

from .models import AdminUser, AdminLoginRequest
from .auth import get_current_admin_user, create_access_token
from .registry import AdminRegistry
from .crud import (get_pending_payouts, process_payout, 
                   get_payout_statistics, get_pending_payouts_for_csv, bulk_process_payouts)
from core.config import JWT_SECRET_KEY, JWT_ALGORITHM
from data.models.models import Payout
from .background_tasks import process_payouts_background

router = APIRouter(prefix="/admin", tags=["Admin Panel"])

# Setup templates and static files
templates = Jinja2Templates(directory="admin/templates")

# Add custom filter for safe JSON serialization
def safe_json_filter(value):
    """Safely serialize values to JSON, handling datetime and other non-serializable types."""
    try:
        if isinstance(value, datetime):
            return value.isoformat()
        elif hasattr(value, 'dict'):
            # For Pydantic models, convert to dict first
            dict_value = value.dict()
            # Handle datetime objects in the dict
            for k, v in dict_value.items():
                if isinstance(v, datetime):
                    dict_value[k] = v.isoformat()
            return json.dumps(dict_value, indent=2)
        else:
            return json.dumps(value, indent=2, default=str)
    except (TypeError, ValueError):
        return str(value)

# Register the custom filter
templates.env.filters['safe_json'] = safe_json_filter

# Helper function to serialize documents with datetime handling
def serialize_document_for_template(doc) -> Dict[str, Any]:
    """Convert document to dict with JSON-serializable values."""
    if hasattr(doc, 'dict'):
        doc_dict = doc.dict()
    else:
        doc_dict = dict(doc) if hasattr(doc, '__iter__') else {}
    
    # Convert ObjectId to string
    if hasattr(doc, 'id'):
        doc_dict['id'] = str(doc.id)
    
    # Handle different data types for template rendering
    for key, value in doc_dict.items():
        if isinstance(value, datetime):
            # Keep datetime objects as is for template - don't convert to string here
            continue
        elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, list, dict)):
            # Convert complex objects to dict
            doc_dict[key] = str(value)
        elif isinstance(value, Decimal):
            doc_dict[key] = float(value)
    
    return doc_dict

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, admin_user: AdminUser = Depends(get_current_admin_user)):
    """Main admin dashboard."""
    # Get statistics
    total_collections = len(AdminRegistry.get_registered_models())
    collections_info = []
    
    for model_name, model_class in AdminRegistry.get_registered_models().items():
        try:
            count = await model_class.count()
            collections_info.append({
                "name": model_name,
                "count": count,
                "verbose_name": AdminRegistry.get_verbose_name(model_name)
            })
        except Exception as e:
            collections_info.append({
                "name": model_name,
                "count": 0,
                "verbose_name": AdminRegistry.get_verbose_name(model_name),
                "error": str(e)
            })
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "admin_user": admin_user,
        "total_collections": total_collections,
        "collections_info": collections_info,
        "collections": AdminRegistry.get_registered_models()
    })


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """Admin login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle admin login."""
    admin_user = await AdminUser.find_one(AdminUser.username == username)
    
    if not admin_user or not pwd_context.verify(password, admin_user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
    if not admin_user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Account is disabled"
        })
    
    # Update last login
    admin_user.last_login = datetime.utcnow()
    await admin_user.save()
    
    # Create access token
    access_token = create_access_token(data={"sub": admin_user.username})
    
    # Redirect to dashboard with token in cookie
    response = RedirectResponse(url="/admin/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="admin_token",
        value=access_token,
        httponly=True,
        max_age=1800,  # 30 minutes
        secure=False  # Set to True in production with HTTPS
    )
    return response


@router.get("/logout")
async def admin_logout():
    """Handle admin logout."""
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("admin_token")
    return response


@router.get("/collection/{model_name}", response_class=HTMLResponse)
async def collection_list(
    request: Request,
    model_name: str,
    page: int = 1,
    limit: int = 20,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """List documents in a collection."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Calculate pagination
    skip = (page - 1) * limit
    total = await model_class.count()
    total_pages = (total + limit - 1) // limit
    
    # Get documents
    documents = await model_class.find().skip(skip).limit(limit).to_list()
    
    # Convert documents to dict format for template
    documents_data = []
    for doc in documents:
        doc_dict = serialize_document_for_template(doc)
        documents_data.append(doc_dict)
    
    # Get field metadata
    field_info = AdminRegistry.get_field_info(model_name)
    
    return templates.TemplateResponse("collection_list.html", {
        "request": request,
        "admin_user": admin_user,
        "model_name": model_name,
        "verbose_name": AdminRegistry.get_verbose_name(model_name),
        "documents": documents_data,
        "field_info": field_info,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < total_pages else None,
        "collections": AdminRegistry.get_registered_models()
    })


@router.get("/collection/{model_name}/create", response_class=HTMLResponse)
async def collection_create_form(
    request: Request,
    model_name: str,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Show form to create new document - separates editable from readonly fields."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    field_info = AdminRegistry.get_field_info(model_name)
    editable_fields = AdminRegistry.get_editable_fields(model_name)
    readonly_fields = AdminRegistry.get_readonly_fields(model_name)
    
    return templates.TemplateResponse("document_form.html", {
        "request": request,
        "admin_user": admin_user,
        "model_name": model_name,
        "verbose_name": AdminRegistry.get_verbose_name(model_name),
        "field_info": field_info,
        "editable_fields": editable_fields,
        "readonly_fields": readonly_fields,
        "is_edit": False,
        "document": {},
        "collections": AdminRegistry.get_registered_models()
    })


@router.post("/collection/{model_name}/create")
async def collection_create(
    request: Request,
    model_name: str,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Handle document creation - SAFE MODE: only processes editable fields."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get form data
    form_data = await request.form()
    form_dict = dict(form_data)
    
    try:
        # SAFE PROCESSING: Only process editable fields
        safe_data = AdminRegistry.process_form_data(model_name, form_dict)
        
        if not safe_data:
            raise ValueError("No valid editable fields provided")
        
        # Create document with only safe data
        print(f"[ADMIN CREATE] Creating {model_name} with safe fields: {list(safe_data.keys())}")
        document = model_class.model_validate(safe_data)
        await document.save()
        
        print(f"[ADMIN CREATE] Successfully created {model_name} document with ID: {document.id}")
        return RedirectResponse(
            url=f"/admin/collection/{model_name}",
            status_code=status.HTTP_302_FOUND
        )
        
    except Exception as e:
        print(f"[ADMIN CREATE] Error creating {model_name}: {str(e)}")
        field_info = AdminRegistry.get_field_info(model_name)
        editable_fields = AdminRegistry.get_editable_fields(model_name)
        readonly_fields = AdminRegistry.get_readonly_fields(model_name)
        
        return templates.TemplateResponse("document_form.html", {
            "request": request,
            "admin_user": admin_user,
            "model_name": model_name,
            "verbose_name": AdminRegistry.get_verbose_name(model_name),
            "field_info": field_info,
            "editable_fields": editable_fields,
            "readonly_fields": readonly_fields,
            "is_edit": False,
            "document": form_dict,
            "error": str(e),
            "collections": AdminRegistry.get_registered_models()
        })


@router.get("/collection/{model_name}/edit/{document_id}", response_class=HTMLResponse)
async def collection_edit_form(
    request: Request,
    model_name: str,
    document_id: str,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Show form to edit document - separates editable from readonly fields."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get document
    document = await model_class.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    field_info = AdminRegistry.get_field_info(model_name)
    editable_fields = AdminRegistry.get_editable_fields(model_name)
    readonly_fields = AdminRegistry.get_readonly_fields(model_name)
    doc_dict = serialize_document_for_template(document)
    
    return templates.TemplateResponse("document_form.html", {
        "request": request,
        "admin_user": admin_user,
        "model_name": model_name,
        "verbose_name": AdminRegistry.get_verbose_name(model_name),
        "field_info": field_info,
        "editable_fields": editable_fields,
        "readonly_fields": readonly_fields,
        "is_edit": True,
        "document": doc_dict,
        "document_id": document_id,
        "collections": AdminRegistry.get_registered_models()
    })


@router.post("/collection/{model_name}/edit/{document_id}")
async def collection_edit(
    request: Request,
    model_name: str,
    document_id: str,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Handle document editing - SAFE MODE: only processes editable fields."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get document
    document = await model_class.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get form data
    form_data = await request.form()
    form_dict = dict(form_data)
    
    try:
        # SAFE PROCESSING: Only process editable fields
        safe_data = AdminRegistry.process_form_data(model_name, form_dict)
        
        if not safe_data:
            print(f"[ADMIN EDIT] No valid editable fields provided for {model_name}")
            raise ValueError("No valid editable fields provided")
        
        print(f"[ADMIN EDIT] Updating {model_name} document {document_id} with safe fields: {list(safe_data.keys())}")
        
        # Update only the safe fields on existing document
        for field_name, value in safe_data.items():
            if hasattr(document, field_name):
                old_value = getattr(document, field_name, None)
                setattr(document, field_name, value)
                print(f"[ADMIN EDIT] Updated {field_name}: {old_value} -> {value}")
        
        # Save the document
        await document.save()
        
        print(f"[ADMIN EDIT] Successfully updated {model_name} document {document_id}")
        return RedirectResponse(
            url=f"/admin/collection/{model_name}",
            status_code=status.HTTP_302_FOUND
        )
        
    except Exception as e:
        print(f"[ADMIN EDIT] Error updating {model_name} document {document_id}: {str(e)}")
        field_info = AdminRegistry.get_field_info(model_name)
        editable_fields = AdminRegistry.get_editable_fields(model_name)
        readonly_fields = AdminRegistry.get_readonly_fields(model_name)
        doc_dict = serialize_document_for_template(document)
        
        return templates.TemplateResponse("document_form.html", {
            "request": request,
            "admin_user": admin_user,
            "model_name": model_name,
            "verbose_name": AdminRegistry.get_verbose_name(model_name),
            "field_info": field_info,
            "editable_fields": editable_fields,
            "readonly_fields": readonly_fields,
            "is_edit": True,
            "document": doc_dict,
            "document_id": document_id,
            "error": str(e),
            "collections": AdminRegistry.get_registered_models()
        })


@router.post("/collection/{model_name}/delete/{document_id}")
async def collection_delete(
    model_name: str,
    document_id: str,
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Handle document deletion."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get and delete document
    document = await model_class.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    await document.delete()
    
    return RedirectResponse(
        url=f"/admin/collection/{model_name}",
        status_code=status.HTTP_302_FOUND
    )


# === PAYOUT MANAGEMENT ENDPOINTS ===

@router.get("/payouts/pending", response_class=HTMLResponse)
async def admin_pending_payouts(
    request: Request, 
    admin_user: AdminUser = Depends(get_current_admin_user),
    csv_success: int = None,
    csv_error: int = None,
    count: int = None,
    error_msg: str = None
):
    """View pending payouts that need admin approval."""
    pending_payouts = await get_pending_payouts()
    stats = await get_payout_statistics()
    
    # Handle CSV upload feedback
    message = None
    message_type = None
    
    if csv_success == 1 and count:
        message = f"✅ CSV uploaded successfully!\n📊 Processing {count} payouts in the background.\n⏳ You can safely close this browser - processing will continue.\n🔄 Refresh this page later to see updated results."
        message_type = "success"
    elif csv_error == 1:
        if error_msg:
            from urllib.parse import unquote
            message = unquote(error_msg)
        else:
            message = "CSV upload failed. Please check your file and try again."
        message_type = "error"
    
    return templates.TemplateResponse("payout_management.html", {
        "request": request,
        "admin_user": admin_user,
        "pending_payouts": pending_payouts,
        "stats": stats,
        "collections": AdminRegistry.get_registered_models(),
        "success": message if message_type == "success" else None,
        "error": message if message_type == "error" else None
    })


@router.post("/payouts/{payout_id}/process")
async def admin_process_payout(
    request: Request,
    payout_id: str,
    action: str = Form(...),  # "approve" or "reject"
    admin_notes: str = Form(""),
    rejection_reason: str = Form(""),
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Process a payout (approve or reject)."""
    try:

        
        # Validate payout_id format
        try:
            payout_obj_id = PydanticObjectId(payout_id)
        except Exception as e:
            print(f"Invalid payout ID format: {payout_id}, error: {e}")
            raise HTTPException(status_code=400, detail="Invalid payout ID format")
        
        # Validate action
        if action not in ["approve", "reject"]:
            print(f"Invalid action: {action}")
            raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'reject'")
        
        # For reject action, ensure rejection_reason is provided
        if action == "reject" and not rejection_reason.strip():
            print("Rejection attempted without reason")
            raise HTTPException(status_code=400, detail="Rejection reason is required when rejecting a payout")
        
        print(f"Processing payout {payout_id} with action '{action}' by admin {admin_user.username}")
        
        result = await process_payout(
            payout_id=payout_obj_id,
            admin_username=admin_user.username,
            action=action,
            admin_notes=admin_notes.strip() if admin_notes.strip() else None,
            rejection_reason=rejection_reason.strip() if rejection_reason.strip() else None
        )
        
        print(f"Payout processed successfully: {result.status}")
        
        return RedirectResponse(
            url="/admin/payouts/pending",
            status_code=status.HTTP_302_FOUND
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error processing payout {payout_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred while processing the payout: {str(e)}")





@router.get("/api/payouts/stats")
async def admin_payout_stats_api(admin_user: AdminUser = Depends(get_current_admin_user)):
    """API endpoint for payout statistics (for AJAX calls)."""
    return await get_payout_statistics()


# === CSV BULK PAYOUT ENDPOINTS ===

@router.get("/payouts/export-csv")
async def export_pending_payouts_csv(admin_user: AdminUser = Depends(get_current_admin_user)):
    """Export all pending payouts to CSV for bulk processing."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    
    # Get pending payouts data
    csv_data = await get_pending_payouts_for_csv()
    
    if not csv_data:
        raise HTTPException(status_code=404, detail="No pending payouts found")
    
    # Create CSV content
    output = io.StringIO()
    fieldnames = [
        'payout_id', 'user_id', 'username', 'amount_hc', 'amount_kwanza', 
        'payout_method', 'phone_number', 'full_name', 'national_id', 
        'crypto_wallet_address', 'crypto_network', 'created_at', 'action', 'admin_notes', 'rejection_reason'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(csv_data)
    
    # Create response
    csv_content = output.getvalue()
    output.close()
    
    # Generate filename with timestamp
    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"pending_payouts_{timestamp}.csv"
    
    # Return as streaming response
    def iter_csv():
        yield csv_content
    
    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )



@router.post("/payouts/import-csv")
async def import_payouts_csv(
    background_tasks: BackgroundTasks,
    csv_file: UploadFile = File(...),
    admin_user: AdminUser = Depends(get_current_admin_user)
):
    """Import CSV file to bulk process payouts - validate and start background processing."""
    import csv
    import io
    from .models import PayoutCSVImportRow
    from beanie.operators import In
    
    # Basic file validation
    if not csv_file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    
    # Read and parse CSV
    csv_content = await csv_file.read()
    csv_text = csv_content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(csv_text))
    
    # Check required columns
    required_columns = ['payout_id', 'action']
    missing_columns = [col for col in required_columns if col not in csv_reader.fieldnames]
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(missing_columns)}")
    
    # Pre-process CSV to get IDs for batch fetch
    rows = list(csv_reader)
    payout_ids_to_fetch = []
    
    for row in rows:
        pid = row.get('payout_id', '').strip()
        if pid:
            try:
                payout_ids_to_fetch.append(PydanticObjectId(pid))
            except:
                pass # Invalid IDs will be caught in main loop
                
    # --- OPTIMIZATION: BATCH FETCH (N+1 FIX) ---
    # Fetch all payouts in one query instead of one per row
    payouts_batch = await Payout.find(In(Payout.id, payout_ids_to_fetch)).to_list()
    payout_map = {str(p.id): p for p in payouts_batch}
    
    validation_errors = []
    payouts_to_process = []
    skipped_count = 0
    
    for row_num, row in enumerate(rows, start=2):
        payout_id = row.get('payout_id', '').strip()
        action = row.get('action', '').strip()
        admin_notes = row.get('admin_notes', '').strip()
        rejection_reason = row.get('rejection_reason', '').strip()
        
        # Skip empty rows
        if not action and not payout_id:
            continue
        
        # Basic validation
        if not payout_id or not action:
            validation_errors.append(f"Row {row_num}: Missing payout_id or action")
            continue
        
        if action.lower() not in ['approve', 'reject']:
            validation_errors.append(f"Row {row_num}: Action must be 'approve' or 'reject'")
            continue
        
        if action.lower() == 'reject' and not rejection_reason.strip():
            validation_errors.append(f"Row {row_num}: Rejection reason required for 'reject' action")
            continue
        
        # Validate payout exists
        payout = payout_map.get(payout_id)
        if not payout:
            validation_errors.append(f"Row {row_num}: Payout {payout_id} not found")
            continue
            
        # --- IDEMPOTENCY FIX ---
        # If payout is NOT pending, just skip it (it's already processed)
        # This allows safe re-uploads of the same CSV
        if payout.status != 'pending':
            skipped_count += 1
            print(f"Skipping row {row_num}: Payout {payout_id} already processed (status: {payout.status})")
            continue
        
        # Add to processing list
        payouts_to_process.append({
            'payout_id': payout_id,
            'action': action.lower(),
            'admin_notes': admin_notes,
            'rejection_reason': rejection_reason
        })
    
    # If validation errors, return to pending page with error
    if validation_errors:
        from urllib.parse import quote
        error_summary = f"CSV validation failed: {len(validation_errors)} errors found"
        error_details = "\\n".join(validation_errors[:5])  # Show first 5 errors
        if len(validation_errors) > 5:
            error_details += f"\\n... and {len(validation_errors) - 5} more errors"
        
        full_error = f"{error_summary}\\n\\n{error_details}"
        encoded_error = quote(full_error[:400])  # URL-encode and limit length
        
        return RedirectResponse(
            url=f"/admin/payouts/pending?csv_error=1&error_msg={encoded_error}",
            status_code=status.HTTP_302_FOUND
        )
    
    if not payouts_to_process and skipped_count == 0:
        return RedirectResponse(
            url="/admin/payouts/pending?csv_error=1&error_msg=No valid payouts found to process",
            status_code=status.HTTP_302_FOUND
        )
        
    if not payouts_to_process and skipped_count > 0:
         return RedirectResponse(
             # Special message for "All skipped"
            url=f"/admin/payouts/pending?csv_error=1&error_msg=All {skipped_count} payouts in CSV were already processed (skipped).",
            status_code=status.HTTP_302_FOUND
        )
    
    # Start background processing
    background_tasks.add_task(process_payouts_background, payouts_to_process, admin_user.username)
    
    # Redirect with success - include skipped info in message
    msg = f"Processing {len(payouts_to_process)} payouts."
    if skipped_count > 0:
        msg += f" (Skipped {skipped_count} already processed)"
        
    from urllib.parse import quote
    return RedirectResponse(
        url=f"/admin/payouts/pending?csv_success=1&count={len(payouts_to_process)}",
        status_code=status.HTTP_302_FOUND
    )
