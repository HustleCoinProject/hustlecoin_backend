# admin/routes.py
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
from decimal import Decimal
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from jose import JWTError, jwt
from beanie import Document
from pydantic import BaseModel

from .models import AdminUser, AdminLoginRequest
from .auth import get_current_admin_user, create_access_token
from .registry import AdminRegistry
from .crud import (get_pending_payouts, process_payout, 
                   get_payout_statistics)
from core.config import JWT_SECRET_KEY, JWT_ALGORITHM

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
    """Show form to create new document."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    field_info = AdminRegistry.get_field_info(model_name)
    
    return templates.TemplateResponse("document_form.html", {
        "request": request,
        "admin_user": admin_user,
        "model_name": model_name,
        "verbose_name": AdminRegistry.get_verbose_name(model_name),
        "field_info": field_info,
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
    """Handle document creation."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get form data
    form_data = await request.form()
    
    try:
        # Convert form data to document data
        doc_data = AdminRegistry.process_form_data(model_name, dict(form_data))
        
        # Create document with validation
        try:
            document = model_class(**doc_data)
            # This will trigger Pydantic validation
            document.model_validate(document.dict())
        except Exception as validation_error:
            raise ValueError(f"Validation failed: {validation_error}")
        
        await document.save()
        
        return RedirectResponse(
            url=f"/admin/collection/{model_name}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        field_info = AdminRegistry.get_field_info(model_name)
        return templates.TemplateResponse("document_form.html", {
            "request": request,
            "admin_user": admin_user,
            "model_name": model_name,
            "verbose_name": AdminRegistry.get_verbose_name(model_name),
            "field_info": field_info,
            "is_edit": False,
            "document": dict(form_data),
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
    """Show form to edit document."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get document
    document = await model_class.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    field_info = AdminRegistry.get_field_info(model_name)
    doc_dict = serialize_document_for_template(document)
    
    return templates.TemplateResponse("document_form.html", {
        "request": request,
        "admin_user": admin_user,
        "model_name": model_name,
        "verbose_name": AdminRegistry.get_verbose_name(model_name),
        "field_info": field_info,
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
    """Handle document editing."""
    model_class = AdminRegistry.get_model(model_name)
    if not model_class:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Get document
    document = await model_class.get(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get form data
    form_data = await request.form()
    
    try:
        # Convert form data to document data
        doc_data = AdminRegistry.process_form_data(model_name, dict(form_data))
        
        # Create a backup of the original document data before modification
        original_data = document.dict()
        
        # Update document fields safely
        updated_fields = []
        for key, value in doc_data.items():
            if hasattr(document, key):
                try:
                    setattr(document, key, value)
                    updated_fields.append(key)
                except Exception as field_error:
                    print(f"Warning: Failed to set field '{key}': {field_error}")
                    continue
        
        # Validate the document before saving
        try:
            # This will trigger Pydantic validation
            document.model_validate(document.dict())
        except Exception as validation_error:
            # Restore original data if validation fails
            for field in updated_fields:
                if field in original_data:
                    setattr(document, field, original_data[field])
            raise ValueError(f"Validation failed: {validation_error}")
        
        # Save the document
        await document.save()
        
        return RedirectResponse(
            url=f"/admin/collection/{model_name}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        field_info = AdminRegistry.get_field_info(model_name)
        doc_dict = serialize_document_for_template(document)
        
        return templates.TemplateResponse("document_form.html", {
            "request": request,
            "admin_user": admin_user,
            "model_name": model_name,
            "verbose_name": AdminRegistry.get_verbose_name(model_name),
            "field_info": field_info,
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
async def admin_pending_payouts(request: Request, admin_user: AdminUser = Depends(get_current_admin_user)):
    """View pending payouts that need admin approval."""
    pending_payouts = await get_pending_payouts()
    stats = await get_payout_statistics()
    
    return templates.TemplateResponse("payout_management.html", {
        "request": request,
        "admin_user": admin_user,
        "pending_payouts": pending_payouts,
        "stats": stats,
        "collections": AdminRegistry.get_registered_models()
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
        from beanie import PydanticObjectId
        
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
