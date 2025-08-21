# API Request/Response Structure Changes

## 📋 ENDPOINT COMPARISON: BEFORE vs AFTER

---

## 1. `POST /api/users/login`

### **BEFORE Implementation:**

#### Request Structure:
```http
POST /api/users/login
Content-Type: application/x-www-form-urlencoded

username=john_doe&password=mypassword123
```

#### Response Structure:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5MjcyMDAwMH0.signature_here",
  "token_type": "bearer"
}
```

#### Token Details (BEFORE):
- **access_token**: Expires in 24 hours (1440 minutes)
- **Token payload**: `{"sub": "john_doe", "exp": 1692720000}`

---

### **AFTER Implementation:**

#### Request Structure:
```http
POST /api/users/login
Content-Type: application/x-www-form-urlencoded

username=john_doe&password=mypassword123
```
**⚠️ REQUEST UNCHANGED** - Same structure as before

#### Response Structure:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5MjgwNjQwMCwidHlwZSI6ImFjY2VzcyJ9.new_signature",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5ODA0ODAwMCwidHlwZSI6InJlZnJlc2gifQ.refresh_signature",
  "token_type": "bearer"
}
```

#### Token Details (AFTER):
- **access_token**: Expires in 48 hours (2880 minutes)
- **refresh_token**: Expires in 60 days
- **Access token payload**: `{"sub": "john_doe", "exp": 1692806400, "type": "access"}`
- **Refresh token payload**: `{"sub": "john_doe", "exp": 1698048000, "type": "refresh"}`

---

## 2. `POST /api/users/refresh` (NEW ENDPOINT)

### **BEFORE Implementation:**
**❌ ENDPOINT DID NOT EXIST**

---

### **AFTER Implementation:**

#### Request Structure:
```http
POST /api/users/refresh
Content-Type: application/json

{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5ODA0ODAwMCwidHlwZSI6InJlZnJlc2gifQ.refresh_signature"
}
```

#### Response Structure:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5MjgwNjQwMCwidHlwZSI6ImFjY2VzcyJ9.new_access_signature",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5ODA0ODAwMCwidHlwZSI6InJlZnJlc2gifQ.new_refresh_signature",
  "token_type": "bearer"
}
```

#### Success Response (200):
- Returns **NEW** access token and refresh token pair
- Both tokens have updated expiration times
- Old refresh token becomes invalid (token rotation)

#### Error Response (401):
```json
{
  "detail": "Invalid refresh token"
}
```

---

## 3. Protected Endpoints (e.g., `GET /api/users/me`)

### **BEFORE Implementation:**

#### Request Structure:
```http
GET /api/users/me
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5MjcyMDAwMH0.signature_here
```

#### Response Structure:
```json
{
  "id": "64f1a2b3c4d5e6f7g8h9i0j1",
  "username": "john_doe",
  "email": "john@example.com",
  "hc_balance": 1500,
  "level": 3,
  "current_hustle": {
    "Freelancer": "Freelancer"
  },
  "level_entry_date": "2024-08-15T10:30:00",
  "hc_earned_in_level": 750,
  "language": "en",
  "task_cooldowns": {},
  "daily_streak": 5,
  "createdAt": "2024-08-01T09:15:00"
}
```

---

### **AFTER Implementation:**

#### Request Structure:
```http
GET /api/users/me
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqb2huX2RvZSIsImV4cCI6MTY5MjgwNjQwMCwidHlwZSI6ImFjY2VzcyJ9.new_signature
```
**⚠️ REQUEST STRUCTURE UNCHANGED** - Still uses access token in Authorization header

#### Response Structure:
```json
{
  "id": "64f1a2b3c4d5e6f7g8h9i0j1",
  "username": "john_doe",
  "email": "john@example.com",
  "hc_balance": 1500,
  "level": 3,
  "current_hustle": {
    "Freelancer": "Freelancer"
  },
  "level_entry_date": "2024-08-15T10:30:00",
  "hc_earned_in_level": 750,
  "language": "en",
  "task_cooldowns": {},
  "daily_streak": 5,
  "createdAt": "2024-08-01T09:15:00"
}
```
**⚠️ RESPONSE STRUCTURE UNCHANGED** - Identical response format

#### New Error Behavior:
- **401 Unauthorized** if access token is expired (frontend should auto-refresh)
- **401 Unauthorized** if token type is not "access" (e.g., if refresh token is used)

---

## 📊 SUMMARY TABLE

| Endpoint | Request Changes | Response Changes | New Fields |
|----------|----------------|------------------|------------|
| `POST /api/users/login` | ✅ None | ➕ `refresh_token` added | `refresh_token` |
| `POST /api/users/refresh` | 🆕 New endpoint | 🆕 New endpoint | All fields new |
| `GET /api/users/me` | ✅ None | ✅ None | None |
| Other protected endpoints | ✅ None | ✅ None | None |

---

## 🔄 TOKEN PAYLOAD COMPARISON

### Access Token Payload

#### BEFORE:
```json
{
  "sub": "john_doe",
  "exp": 1692720000
}
```

#### AFTER:
```json
{
  "sub": "john_doe",
  "exp": 1692806400,
  "type": "access"
}
```

### Refresh Token Payload (NEW)

#### AFTER:
```json
{
  "sub": "john_doe",
  "exp": 1698048000,
  "type": "refresh"
}
```

---

## 🚨 BREAKING CHANGES

**NONE** - All changes are backward compatible:

1. **Login endpoint** adds `refresh_token` field (additive change)
2. **Protected endpoints** work exactly the same
3. **Access token** format enhanced but compatible
4. **Request structures** unchanged for existing endpoints

The only **new requirement** is handling the additional `refresh_token` field in login responses and implementing the new refresh endpoint for optimal user experience.
