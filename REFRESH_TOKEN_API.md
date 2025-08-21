#!/usr/bin/env python3
"""
API Documentation for Refresh Token Implementation

This document shows the updated API endpoints and usage examples
for the new refresh token functionality.
"""

## UPDATED ENDPOINTS:

### 1. POST /api/users/login
**Description**: Login and receive access + refresh tokens
**Request Body**: OAuth2PasswordRequestForm (username, password)
**Response**: 
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### 2. POST /api/users/refresh (NEW)
**Description**: Refresh access token using refresh token
**Request Body**:
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```
**Response**:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

## TOKEN SPECIFICATIONS:

### Access Token:
- **Expiry**: 48 hours (2880 minutes)
- **Type**: "access" (stored in JWT payload)
- **Usage**: Authentication for protected endpoints
- **Header**: Authorization: Bearer {access_token}

### Refresh Token:
- **Expiry**: 60 days
- **Type**: "refresh" (stored in JWT payload)
- **Usage**: Generate new access/refresh token pairs
- **Stateless**: No database storage required
- **Security**: Contains same secret key validation as access tokens

## USAGE FLOW:

1. **Initial Login**:
   ```
   POST /api/users/login
   Body: { username: "user", password: "pass" }
   -> Returns: { access_token, refresh_token, token_type }
   ```

2. **Use Access Token**:
   ```
   GET /api/users/me
   Headers: { Authorization: "Bearer {access_token}" }
   -> Returns: User profile data
   ```

3. **Refresh When Access Token Expires**:
   ```
   POST /api/users/refresh
   Body: { refresh_token: "..." }
   -> Returns: { new_access_token, new_refresh_token, token_type }
   ```

4. **Continue with New Tokens**:
   - Use new access_token for API calls
   - Store new refresh_token for future refreshes

## SECURITY FEATURES:

- ✅ Stateless design (no database storage)
- ✅ JWT signature verification
- ✅ Token type validation (access vs refresh)
- ✅ User existence validation on refresh
- ✅ Automatic token rotation on refresh
- ✅ Configurable expiration times

## CONFIGURATION:

In `core/config.py`:
```python
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 48  # 48 hours
REFRESH_TOKEN_EXPIRE_DAYS: int = 60         # 60 days
```

## ERROR HANDLING:

- **401 Unauthorized**: Invalid/expired refresh token
- **401 Unauthorized**: Invalid access token
- **400 Bad Request**: Malformed token request
