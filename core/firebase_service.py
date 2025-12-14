"""
Firebase Authentication Service for Backend
Handles Firebase ID token verification
"""

import firebase_admin
from firebase_admin import credentials, auth
from fastapi import HTTPException, status
from typing import Dict, Optional
import os
import json
from .config import settings


class FirebaseService:
    """Service for Firebase operations"""
    
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Initialize Firebase Admin SDK"""
        if cls._initialized:
            print("⚠️  Firebase already initialized")
            return
            
        try:
            # Option 1: Check for base64-encoded credentials (recommended for production)
            service_account_base64 = settings.FIREBASE_SERVICE_ACCOUNT_BASE64
            
            if service_account_base64:
                # Decode base64 to JSON
                import base64
                service_account_json = base64.b64decode(service_account_base64).decode('utf-8')
                service_account_dict = json.loads(service_account_json)
                cred = credentials.Certificate(service_account_dict)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase initialized with base64-encoded credentials")
                print(f"   Project ID: {service_account_dict.get('project_id')}")
            else:
                # Option 2: Check for file path (local development)
                service_account_path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
                
                if service_account_path and os.path.exists(service_account_path):
                    # Initialize with service account file
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    
                    # Read and show project ID
                    with open(service_account_path, 'r') as f:
                        sa_data = json.load(f)
                        project_id = sa_data.get('project_id')
                        print(f"✅ Firebase initialized with service account file")
                        print(f"   File: {service_account_path}")
                        print(f"   Project ID: {project_id}")
                else:
                    # Option 3: Initialize with application default credentials (development)
                    # This works when you've run `firebase login` or set GOOGLE_APPLICATION_CREDENTIALS
                    firebase_admin.initialize_app()
                    print("✅ Firebase initialized with default credentials")
                
            cls._initialized = True
            print("✅ Firebase Admin SDK initialized successfully")
            
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️  Firebase authentication will not be available")
            # Don't raise exception - allow app to start without Firebase
    
    @classmethod
    async def verify_firebase_token(cls, id_token: str) -> Dict[str, any]:
        """
        Verify Firebase ID token and return user information
        
        Args:
            id_token: Firebase ID token from the client
            
        Returns:
            Dictionary containing user information (uid, email, name, etc.)
            
        Raises:
            HTTPException: If token is invalid or verification fails
        """
        if not cls._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Firebase service not initialized"
            )
        
        try:
            print(f"🔍 Attempting to verify Firebase token (length: {len(id_token)})")
            print(f"🔍 Token preview: {id_token[:50]}...")
            
            # Use PyJWT to verify token with custom options
            # We verify signature and expiry, but skip issued-at time check to avoid clock skew issues
            import jwt
            from jwt import PyJWKClient
            
            # Get Google's public keys for Firebase
            jwks_url = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
            jwks_client = PyJWKClient(jwks_url)
            
            # Get the signing key from the token
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            
            # Verify token: check signature and expiry, but not issued-at time
            decoded_token = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=firebase_admin.get_app().project_id,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": False,  # Skip issued-at time check (avoids clock skew issues)
                    "verify_aud": True
                }
            )
            
            print(f"✅ Token verified successfully for user: {decoded_token.get('email')}")
            
            # Extract user information
            user_info = {
                "uid": decoded_token.get("uid") or decoded_token.get("user_id") or decoded_token.get("sub"),
                "email": decoded_token.get("email"),
                "email_verified": decoded_token.get("email_verified", False),
                "name": decoded_token.get("name"),
                "picture": decoded_token.get("picture"),
                "firebase_user": True
            }
            
            return user_info
            
        except auth.InvalidIdTokenError as e:
            print(f"❌ InvalidIdTokenError: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Firebase ID token"
            )
        except auth.ExpiredIdTokenError as e:
            print(f"❌ ExpiredIdTokenError: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Firebase ID token has expired"
            )
        except ValueError as e:
            print(f"❌ ValueError during token verification: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token format: {str(e)}"
            )
        except Exception as e:
            print(f"❌ Unexpected error verifying Firebase token: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to verify Firebase token: {str(e)}"
            )


# Initialize Firebase when module is imported
FirebaseService.initialize()
