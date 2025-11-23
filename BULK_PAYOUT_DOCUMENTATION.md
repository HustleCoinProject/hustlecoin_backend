# Bulk Payout Processing with CSV Export/Import

## Overview

The HustleCoin admin panel now supports bulk approval/rejection of payout requests through CSV export/import functionality. This feature is designed to handle mass payout processing efficiently when the application scales.

## Features

### 1. CSV Export
- **Endpoint**: `GET /admin/payouts/export-csv`
- **Function**: Downloads all pending payouts as a CSV file
- **File Format**: `pending_payouts_YYYYMMDD_HHMMSS.csv`

### 2. CSV Import
- **Endpoint**: `POST /admin/payouts/import-csv`
- **Function**: Processes payouts in bulk based on CSV content
- **Validation**: Ensures proper action values and rejection reasons

### 3. Admin Interface
- **Export Button**: Download pending payouts CSV
- **Import Button**: Upload and process modified CSV
- **Results Display**: Shows processing results with success/error details

## CSV Structure

### Export CSV Fields
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
```

### Required Fields for Import
- `payout_id`: Unique identifier for the payout (auto-filled)
- `action`: Either "approve" or "reject" (admin fills this)
- `admin_notes`: Optional notes (admin fills this)
- `rejection_reason`: Required when action is "reject" (admin fills this)

## How to Use

### Step 1: Export CSV
1. Navigate to Admin Panel → Payout Management
2. Click "Export CSV" button
3. Save the downloaded file to your computer

### Step 2: Fill CSV Decisions
1. Open the CSV file in Excel, Google Sheets, or any spreadsheet application
2. Fill the `action` column with either:
   - `approve` - to approve the payout
   - `reject` - to reject the payout
3. For rejections, fill the `rejection_reason` column with a clear reason
4. Optionally, add notes in the `admin_notes` column
5. Save the file

### Step 3: Import CSV
1. Go back to Admin Panel → Payout Management
2. Click "Import CSV" button
3. Copy the entire CSV content (including headers)
4. Paste it into the text area in the modal
5. Review the preview
6. Click "Process Payouts"

### Step 4: Review Results
- The system will show a summary of processed payouts
- Any errors will be displayed with specific details
- Successfully processed payouts will be updated immediately

## Example Workflow

### 1. Export Example
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
6547e8b5c4d6e7f8a9b1c2d3,6547e8b5c4d6e7f8a9b1c2d4,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789,,,2024-11-19 10:30:00,,,
6547e8b5c4d6e7f8a9b1c2d5,6547e8b5c4d6e7f8a9b1c2d6,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,,,
```

### 2. Filled Example (for import)
```csv
payout_id,user_id,username,amount_hc,amount_kwanza,payout_method,phone_number,full_name,national_id,bank_iban,bank_name,created_at,action,admin_notes,rejection_reason
6547e8b5c4d6e7f8a9b1c2d3,6547e8b5c4d6e7f8a9b1c2d4,john_doe,1000,100.0,multicaixa_express,+244912345678,John Doe,123456789,,,2024-11-19 10:30:00,approve,Verified customer information,
6547e8b5c4d6e7f8a9b1c2d5,6547e8b5c4d6e7f8a9b1c2d6,jane_smith,2000,200.0,bank_transfer,,Jane Smith,,AO06004000000037733218001,Banco BAI,2024-11-19 11:15:00,reject,Customer needs to provide correct IBAN,Invalid IBAN format
```

## Validation Rules

### Action Field
- Must be either "approve" or "reject" (case-insensitive)
- Empty action fields are skipped (not processed)

### Rejection Reason
- Required when action is "reject"
- Must not be empty for rejections

### Payout ID
- Must be a valid MongoDB ObjectId
- Must correspond to an existing pending payout

## Error Handling

The system provides detailed error reporting:

### Common Errors
- **Invalid action**: Action must be "approve" or "reject"
- **Missing rejection reason**: Required when rejecting payouts
- **Payout not found**: Invalid payout ID
- **Payout not pending**: Trying to process already processed payouts
- **User not found**: Associated user doesn't exist

### Error Response Format
```json
{
  "processed": 1,
  "failed": 1,
  "errors": [
    {
      "payout_id": "6547e8b5c4d6e7f8a9b1c2d5",
      "error": "Rejection reason is required when rejecting a payout"
    }
  ],
  "success_details": [
    {
      "payout_id": "6547e8b5c4d6e7f8a9b1c2d3",
      "action": "approve",
      "status": "completed"
    }
  ]
}
```

## Security Features

- **Admin Authentication**: Only authenticated admin users can access these endpoints
- **Validation**: All inputs are validated before processing
- **Transaction Safety**: Each payout is processed individually with proper error handling
- **Audit Trail**: All actions are logged with admin username and timestamps

## Performance Considerations

- **Batch Processing**: Processes multiple payouts efficiently
- **Error Isolation**: One failed payout doesn't stop others from processing
- **Memory Efficient**: Streams CSV content without loading entire file in memory
- **Scalable**: Can handle hundreds of payouts in a single batch

## Technical Implementation

### New Models
- `PayoutCSVExportRow`: Structure for CSV export data
- `PayoutCSVImportRow`: Validation for CSV import data
- `BulkPayoutProcessRequest`: Request model for bulk processing

### New Functions
- `get_pending_payouts_for_csv()`: Fetches data for CSV export
- `bulk_process_payouts()`: Handles bulk payout processing

### New Endpoints
- `GET /admin/payouts/export-csv`: CSV export endpoint
- `POST /admin/payouts/import-csv`: CSV import endpoint

## Best Practices

1. **Always export first**: Get the latest pending payouts before processing
2. **Review carefully**: Double-check decisions before importing
3. **Use clear reasons**: Provide detailed rejection reasons for user transparency
4. **Test with small batches**: Start with a few payouts when learning the system
5. **Keep backups**: Save your filled CSV files for record-keeping

## Troubleshooting

### CSV Format Issues
- Ensure all headers are present
- Use proper CSV formatting (commas as separators)
- Don't modify the payout_id or other system fields

### Import Failures
- Check that all required fields are filled
- Verify payout IDs are valid
- Ensure payouts are still in "pending" status

### Browser Issues
- For large CSV files, consider breaking them into smaller batches
- Ensure your browser doesn't timeout on large imports
- Clear browser cache if you encounter display issues

## Future Enhancements

- **File Upload**: Direct CSV file upload instead of copy-paste
- **Preview Mode**: Show what will happen before actual processing
- **Scheduled Processing**: Ability to schedule bulk processing
- **Advanced Filters**: Export payouts with specific criteria
- **Email Notifications**: Notify admins when bulk processing completes