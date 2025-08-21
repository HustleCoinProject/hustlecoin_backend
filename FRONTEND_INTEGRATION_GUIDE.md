# API Endpoint Changes Summary for Frontend Development

## Overview
The backend has been updated to implement refresh token functionality with stateless JWT tokens. This document outlines all changes that affect frontend integration.

---

## 🔄 CHANGED ENDPOINTS

### 1. `POST /api/users/login`

#### **BEFORE:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### **AFTER:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### **Frontend Changes Required:**
- ✅ Update login response handler to store BOTH tokens
- ✅ Store `refresh_token` in secure storage (localStorage/sessionStorage)
- ✅ Continue using `access_token` for API authentication

---

## ➕ NEW ENDPOINTS

### 2. `POST /api/users/refresh` (NEW)

#### **Purpose:** 
Refresh expired access tokens using refresh token

#### **Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### **Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

#### **Frontend Implementation Required:**
- ✅ Implement automatic token refresh on 401 errors
- ✅ Update stored tokens with new values from response
- ✅ Retry original failed request with new access token

---

## ⏰ TOKEN EXPIRATION CHANGES

### Access Token Expiration
- **BEFORE:** 24 hours (1440 minutes)
- **AFTER:** 48 hours (2880 minutes)

### Refresh Token Expiration (NEW)
- **EXPIRATION:** 60 days
- **PURPOSE:** Generate new access tokens without re-login

---

## 🔧 FRONTEND INTEGRATION GUIDE

### 1. **Token Storage Strategy**
```javascript
// After successful login
const loginResponse = await login(credentials);
localStorage.setItem('access_token', loginResponse.access_token);
localStorage.setItem('refresh_token', loginResponse.refresh_token);
```

### 2. **API Request Interceptor (Recommended)**
```javascript
// Example with Axios
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          const refreshResponse = await axios.post('/api/users/refresh', {
            refresh_token: refreshToken
          });
          
          // Update stored tokens
          localStorage.setItem('access_token', refreshResponse.data.access_token);
          localStorage.setItem('refresh_token', refreshResponse.data.refresh_token);
          
          // Retry original request
          error.config.headers.Authorization = `Bearer ${refreshResponse.data.access_token}`;
          return axios.request(error.config);
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);
```

### 3. **Manual Token Refresh**
```javascript
async function refreshTokens() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }
  
  const response = await fetch('/api/users/refresh', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      refresh_token: refreshToken
    })
  });
  
  if (!response.ok) {
    throw new Error('Token refresh failed');
  }
  
  const data = await response.json();
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  
  return data;
}
```

### 4. **Logout Implementation**
```javascript
function logout() {
  // Clear both tokens
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  
  // Redirect to login page
  window.location.href = '/login';
}
```

---

## 🛡️ SECURITY CONSIDERATIONS

### For Frontend Developers:

1. **Token Storage:**
   - Store tokens in `localStorage` or `sessionStorage`
   - Consider `httpOnly` cookies for enhanced security (requires backend changes)

2. **Token Validation:**
   - Always check token expiration before making API calls
   - Implement automatic refresh before token expires (recommended: 5 minutes before)

3. **Error Handling:**
   - Handle 401 errors gracefully with automatic refresh
   - Provide user feedback during token refresh process
   - Clear tokens and redirect to login if refresh fails

4. **Network Requests:**
   - Continue using `Authorization: Bearer {access_token}` header
   - Never send refresh token in regular API calls (only for `/refresh` endpoint)

---

## 📝 IMPLEMENTATION CHECKLIST

### Immediate Changes Required:
- [ ] Update login response handling to store refresh token
- [ ] Implement `/api/users/refresh` endpoint integration
- [ ] Add automatic token refresh on 401 errors
- [ ] Update logout to clear both tokens
- [ ] Test token refresh flow end-to-end

### Optional Enhancements:
- [ ] Proactive token refresh before expiration
- [ ] Token refresh loading states/indicators
- [ ] Enhanced error handling for refresh failures
- [ ] Security audit of token storage method

---

## 🚨 BREAKING CHANGES

**None** - The changes are backward compatible:
- Login endpoint still returns `access_token` and `token_type`
- All existing protected endpoints work the same way
- Access token format and usage unchanged

The only difference is that login now also returns a `refresh_token` field, which is additive and won't break existing frontend code.

---

## 📞 TESTING

### Test Cases for Frontend:
1. **Login Flow:** Verify both tokens are received and stored
2. **Protected API Calls:** Ensure access token still works normally
3. **Token Refresh:** Test refresh endpoint returns new tokens
4. **Automatic Refresh:** Verify 401 errors trigger refresh flow
5. **Refresh Failure:** Ensure graceful logout when refresh fails
6. **Logout:** Confirm both tokens are cleared

### Sample cURL Commands:
```bash
# Login
curl -X POST "http://localhost:8000/api/users/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=testpass"

# Refresh tokens
curl -X POST "http://localhost:8000/api/users/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"YOUR_REFRESH_TOKEN_HERE"}'
```
