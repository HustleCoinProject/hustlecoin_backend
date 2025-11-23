# CSV Bulk Payout Testing Examples

## Valid CSV Example (will be processed successfully):
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
674c5e8f123456789abcdef0,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,approve,Customer verified,
674c5e8f123456789abcdef2,674c5e8f123456789abcdef3,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,reject,Customer needs to provide correct IBAN,Invalid IBAN format provided
```

## Invalid CSV Examples (will be rejected with specific error messages):

### 1. Missing action column:
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,admin_notes,rejection_reason
674c5e8f123456789abcdef0,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,Customer verified,
```
**Error**: "Missing required columns: action"

### 2. Invalid action values:
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
674c5e8f123456789abcdef0,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,accepted,Customer verified,
674c5e8f123456789abcdef2,674c5e8f123456789abcdef3,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,deny,,Invalid IBAN
```
**Errors**: 
- "Row 2: Invalid action 'accepted' (must be 'approve' or 'reject')"
- "Row 3: Invalid action 'deny' (must be 'approve' or 'reject')"

### 3. Missing rejection reason for reject actions:
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
674c5e8f123456789abcdef0,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,approve,Customer verified,
674c5e8f123456789abcdef2,674c5e8f123456789abcdef3,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,reject,Check IBAN,
```
**Error**: "Row 3: Rejection reason is required when action is 'reject'"

### 4. Invalid payout ID format:
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
invalid-id,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,approve,Customer verified,
674c5e8f123456789abcdef2,674c5e8f123456789abcdef3,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,reject,,Invalid IBAN format
```
**Error**: "Row 2: Invalid payout_id format 'invalid-id'"

### 5. Mixed errors (multiple issues):
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
674c5e8f123456789abcdef0,674c5e8f123456789abcdef1,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789AB,,,2024-11-19 10:30:00,maybe,Customer verified,
invalid-payout-id,674c5e8f123456789abcdef3,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,reject,Check IBAN,
674c5e8f123456789abcdef4,674c5e8f123456789abcdef5,bob_wilson,1500,150.0,multicaixa_express,+244912345679,Bob Wilson,987654321CD,,,2024-11-19 12:00:00,,Admin notes here,
```
**Errors**:
- "Row 2: Invalid action 'maybe' (must be 'approve' or 'reject')"
- "Row 3: Invalid payout_id format 'invalid-payout-id'"
- "Row 3: Rejection reason is required when action is 'reject'"
- "Row 4: Missing action (must be 'approve' or 'reject')"

## Validation Rules Summary:

### ✅ **What Gets Processed:**
- Rows with valid payout_id (MongoDB ObjectId format)
- Action is exactly "approve" or "reject" (case-insensitive)
- For "reject" actions: rejection_reason is filled
- Payout exists in database and has "pending" status
- All validation passes for ALL rows

### ❌ **What Gets Rejected:**
- Missing required columns (payout_id, action)
- Invalid action values (anything other than approve/reject)
- Missing rejection_reason when action is "reject"
- Invalid payout_id format
- Payout not found in database
- Payout not in "pending" status
- ANY validation error in ANY row rejects the entire file

### 🔧 **Processing Behavior:**
- **Pre-validation**: All rows checked before any processing starts
- **All-or-nothing**: Either all rows succeed or nothing is processed
- **Detailed errors**: Shows exactly which rows have which problems
- **File safety**: Original file is not stored on server, only processed in memory
- **Rollback safe**: If processing fails after validation, individual payouts can still fail without affecting others