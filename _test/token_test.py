#!/usr/bin/env python3
"""
Test script to verify refresh token functionality.
This script tests token creation and verification without requiring a running server.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from jose import jwt, JWTError
from core.config import settings
from core.security import create_access_token, create_refresh_token

def test_token_creation():
    """Test that tokens are created with correct types and expiration."""
    username = "testuser"
    
    # Create tokens
    access_token = create_access_token(data={"sub": username})
    refresh_token = create_refresh_token(data={"sub": username})
    
    print(f"Access Token: {access_token[:50]}...")
    print(f"Refresh Token: {refresh_token[:50]}...")
    
    # Decode and verify access token
    try:
        access_payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print(f"Access Token Payload: {access_payload}")
        print(f"Access Token Type: {access_payload.get('type')}")
        print(f"Access Token Expires: {datetime.fromtimestamp(access_payload.get('exp'))}")
        
        # Verify it's an access token
        assert access_payload.get('type') == 'access', "Access token should have type 'access'"
        assert access_payload.get('sub') == username, "Access token should contain correct username"
        
    except JWTError as e:
        print(f"Error decoding access token: {e}")
        return False
    
    # Decode and verify refresh token
    try:
        refresh_payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        print(f"Refresh Token Payload: {refresh_payload}")
        print(f"Refresh Token Type: {refresh_payload.get('type')}")
        print(f"Refresh Token Expires: {datetime.fromtimestamp(refresh_payload.get('exp'))}")
        
        # Verify it's a refresh token
        assert refresh_payload.get('type') == 'refresh', "Refresh token should have type 'refresh'"
        assert refresh_payload.get('sub') == username, "Refresh token should contain correct username"
        
    except JWTError as e:
        print(f"Error decoding refresh token: {e}")
        return False
    
    # Verify expiration times
    access_exp = datetime.fromtimestamp(access_payload.get('exp'))
    refresh_exp = datetime.fromtimestamp(refresh_payload.get('exp'))
    now = datetime.utcnow()
    
    # Access token should expire in about 48 hours
    access_delta = access_exp - now
    expected_access_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    assert abs(access_delta.total_seconds() - expected_access_delta.total_seconds()) < 60, "Access token expiration should be ~48 hours"
    
    # Refresh token should expire in about 60 days
    refresh_delta = refresh_exp - now
    expected_refresh_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    assert abs(refresh_delta.total_seconds() - expected_refresh_delta.total_seconds()) < 60, "Refresh token expiration should be ~60 days"
    
    print("✅ All token tests passed!")
    return True

if __name__ == "__main__":
    print("Testing refresh token implementation...")
    print(f"Settings - Access Token Expire Minutes: {settings.ACCESS_TOKEN_EXPIRE_MINUTES}")
    print(f"Settings - Refresh Token Expire Days: {settings.REFRESH_TOKEN_EXPIRE_DAYS}")
    print("=" * 50)
    
    if test_token_creation():
        print("🎉 Token implementation is working correctly!")
    else:
        print("❌ Token implementation has issues!")
        sys.exit(1)
