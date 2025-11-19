# Payout System Documentation

## Overview

The HustleCoin payout system allows users to convert their HustleCoins (HC) to real Angolan Kwanza (AOA) and withdraw money through two methods:
1. **Multicaixa Express** - Transfer via phone number
2. **Bank Transfer** - Transfer via IBAN

## Key Features

- **Conversion Rate**: Configurable (default: 1 AOA = 10 HC)
- **Minimum Payout**: Configurable (default: 100 HC = 10 AOA)
- **Two Payment Methods**: Multicaixa Express and Bank Transfer
- **Admin Processing**: Manual approval/rejection by admin agents
- **Balance Protection**: HC is deducted on request, returned on rejection
- **Full Audit Trail**: Complete tracking of all payout requests

## Database Models

### User Model (Updated)
Added payout-related fields:
- `phone_number`: For Multicaixa Express transfers
- `full_name`: User's full name for verification
- `national_id`: National ID for verification
- `bank_iban`: IBAN for bank transfers
- `bank_name`: Bank name for transfers

### Payout Model
- `user_id`: Reference to user
- `amount_hc`: Amount in HustleCoin
- `amount_kwanza`: Amount in Kwanza (calculated)
- `conversion_rate`: Rate used for conversion
- `payout_method`: "multicaixa_express" or "bank_transfer"
- `status`: "pending" | "processing" | "completed" | "rejected"
- Payment details (phone/IBAN based on method)
- Admin processing info and timestamps

## API Endpoints

### User Endpoints (`/api/payouts`)

#### Get Payout Methods
```http
GET /api/payouts/methods
```
Returns available payout methods and requirements.

#### Get User Payout Info
```http
GET /api/payouts/info
Authorization: Bearer <token>
```
Returns user's payout information and available balance.

#### Update Payout Info
```http
PUT /api/payouts/info
Authorization: Bearer <token>
Content-Type: application/json

{
  "phone_number": "923456789",
  "full_name": "João Silva",
  "national_id": "123456789LA041",
  "bank_iban": "AO06000000123456789101112",
  "bank_name": "Banco BIC"
}
```

#### Request Payout
```http
POST /api/payouts/request
Authorization: Bearer <token>
Content-Type: application/json

{
  "amount_hc": 500,
  "payout_method": "multicaixa_express",
  "phone_number": "923456789",
  "full_name": "João Silva", 
  "national_id": "123456789LA041"
}
```

#### Get Payout History
```http
GET /api/payouts/history?limit=50&offset=0
Authorization: Bearer <token>
```

#### Get Payout Details
```http
GET /api/payouts/{payout_id}
Authorization: Bearer <token>
```

#### System Status
```http
GET /api/payouts/system/status
```
Returns payout system status and statistics.

### Admin Endpoints (`/admin`)

#### Payout Management Dashboard
```http
GET /admin/payouts/pending
```
View pending payouts requiring approval.

#### Process Payout
```http
POST /admin/payouts/{payout_id}/process
```
Approve or reject a payout request.

#### Complete Payout
```http
POST /admin/payouts/{payout_id}/complete  
```
Mark a processing payout as completed.

#### Payout Statistics API
```http
GET /admin/api/payouts/stats
```
Get payout statistics for dashboard.

## Payout Flow

### 1. User Setup
- User updates payout information via `/api/payouts/info`
- Information is stored in User model for reuse

### 2. Payout Request
- User requests payout via `/api/payouts/request`
- System validates:
  - Sufficient HC balance
  - Required payout fields
  - Minimum payout amount
  - No pending payouts
- HC is immediately deducted from user balance
- Payout created with "pending" status

### 3. Admin Processing
- Admin views pending payouts in admin panel
- Admin can:
  - **Approve**: Changes status to "processing"
  - **Reject**: Changes status to "rejected" and returns HC to user

### 4. Payment Completion
- Admin manually processes payment (external system)
- Admin marks payout as "completed" 
- Process is complete

### 5. Rejection Handling
- If rejected, HC is automatically returned to user
- Rejection reason is recorded
- User can see rejection reason in history

## Configuration

Environment variables in `.env`:
```
PAYOUT_CONVERSION_RATE=10.0      # 1 AOA = 10 HC
MINIMUM_PAYOUT_HC=100            # Minimum 100 HC
MINIMUM_PAYOUT_KWANZA=10.0       # Minimum 10 AOA
```

## Admin Interface

- **Dashboard**: Shows payout statistics
- **Payout Management**: `/admin/payouts/pending` - Process pending payouts
- **Payout Collection**: `/admin/collection/payout` - View all payouts
- **Auto-refresh**: Pending payouts page refreshes every 30 seconds

## Security Features

- JWT authentication for all user endpoints
- Admin authentication for processing
- Balance verification before payout creation
- Atomic operations for balance updates
- Complete audit trail with timestamps
- Input validation and sanitization
- Prevention of duplicate pending payouts

## Payment Methods

### Multicaixa Express
Required fields:
- Phone number (9+ digits)
- Full name
- National ID

### Bank Transfer  
Required fields:
- Bank IBAN (15-34 characters)
- Bank name

## Error Handling

- Insufficient balance
- Invalid payout amounts
- Missing required fields
- Duplicate pending payouts
- Invalid payout methods
- Database connection errors

All errors return appropriate HTTP status codes and descriptive messages.
