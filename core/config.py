# core/config.py
from pydantic_settings import BaseSettings
from typing import Optional
import os
import time
import json
import logging

try:
    import firebase_admin
    from firebase_admin import remote_config
except ImportError:
    firebase_admin = None
    remote_config = None

# Configure logging
logger = logging.getLogger("config")

class ParameterValueWrapper:
    """Mimics the old sdk.remote_config.ParameterValue"""
    def __init__(self, value, source="remote"):
        self.value = value
        self.source = source

class TemplateWrapper:
    """Mimics the old sdk.remote_config.Template"""
    def __init__(self, parameters_dict):
        # parameters_dict is { key: { defaultValue: { value: "..." } } } from API
        self.parameters = {}
        for key, val_obj in parameters_dict.items():
            # Extract the string value from the nested API structure
            # API structure: "parameters": { "KEY": { "defaultValue": { "value": "123" } } }
            default_val = val_obj.get("defaultValue", {})
            val_str = default_val.get("value")
            
            # Populate the wrapper
            self.parameters[key] = type("Param", (), {})()
            self.parameters[key].default_value = ParameterValueWrapper(val_str)

class RemoteConfig:
    """
    Helper to fetch and cache Firebase Remote Config values.
    Priority: Environment Variable > Remote Config > Default
    
    NOTE: Uses direct REST API because firebase-admin v7 removed get_template()
    """
    _instance = None
    _template = None
    _last_fetch_time = 0
    _cache_ttl = 1800  # 30 minutes cache

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RemoteConfig, cls).__new__(cls)
        return cls._instance

    def _get_access_token(self):
        """Get a valid access token using firebase_admin credentials."""
        app = firebase_admin.get_app()
        credential = app.credential.get_credential()
        
        # Refresh if necessary
        import google.auth.transport.requests
        request = google.auth.transport.requests.Request()
        if not credential.valid:
             credential.refresh(request)
             
        return credential.token

    def _fetch_template_via_rest(self):
        """Fetches the client template via Google REST API."""
        try:
            import httpx
            app = firebase_admin.get_app()
            # We need the project ID. It's usually in the credential or options.
            project_id = app.project_id
            if not project_id:
                # Try getting from credential if not on app object directly
                # Service account creds usually have project_id
                if hasattr(app.credential, 'project_id'):
                    project_id = app.credential.project_id
            
            if not project_id:
                logger.error("Could not determine Project ID for Remote Config fetch")
                return None

            token = self._get_access_token()
            url = f"https://firebaseremoteconfig.googleapis.com/v1/projects/{project_id}/remoteConfig"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            # Use a short timeout so we don't block startup too long
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                
            # Parse into our wrapper
            return TemplateWrapper(data.get("parameters", {}))

        except ImportError:
            logger.error("httpx is required for Remote Config fetch but not installed.")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch Remote Config via REST: {e}")
            return None

    def _fetch_template(self):
        """Fetches the template from Firebase if cache is expired."""
        if not firebase_admin:
            return None

        current_time = time.time()
        if self._template and (current_time - self._last_fetch_time < self._cache_ttl):
            return self._template

        # Fetch new
        new_template = self._fetch_template_via_rest()
        if new_template:
            self._template = new_template
            self._last_fetch_time = current_time
            logger.info("✅ Fetched latest Remote Config template (REST)")
        else:
            logger.warning("⚠️ Using cached/empty config due to fetch failure")
            
        return self._template

    def get_value(self, key: str, default: any, cast_type: type = str) -> any:
        """
        Get a config value with priority:
        1. Environment Variable
        2. Firebase Remote Config
        3. Default value
        """
        # 1. Check Environment Variable
        env_val = os.environ.get(key)
        if env_val is not None:
            try:
                return cast_type(env_val)
            except ValueError:
                logger.error(f"❌ Failed to cast env var {key}={env_val} to {cast_type}")

        # 2. Check Remote Config
        template = self._fetch_template()
        if template and key in template.parameters:
            try:
                # Use our wrapper structure
                val_str = template.parameters[key].default_value.value
                if val_str is not None:
                     return cast_type(val_str)
            except Exception as e:
                 logger.debug(f"Could not retrieve {key} from remote config: {e}")

        # 3. Return Default
        return default

# Initialize singleton
remote_config_manager = RemoteConfig()


class Settings(BaseSettings):
    MONGO_DETAILS: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 48  # 48 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 60  # 60 days
    
    # Firebase configuration (optional)
    FIREBASE_SERVICE_ACCOUNT_BASE64: Optional[str] = None  # Base64 encoded service account (for production)
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None  # File path to service account (for local dev)
    
    # Land configuration
    # These are now backed by Remote Config but expose the same interface
    
    @property
    def LAND_PRICE(self) -> int:
        # Default: 2000
        return remote_config_manager.get_value("LAND_BUY_PRICE", 2000, int)

    @property
    def LAND_SELL_PRICE(self) -> int:
        # Default: 1000
        return remote_config_manager.get_value("LAND_SELL_PRICE", 1000, int)
    
    @property
    def H3_TILE_INDEX_RESOLUTION(self) -> int:
        # Default: 8 (from components/land.py)
        return remote_config_manager.get_value("H3_TILE_INDEX_RESOLUTION", 8, int)

    LAND_INCOME_PER_DAY: int = 40
    LAND_INCOME_ACCUMULATE: bool = False  # If True, income accumulates over days; if False, fixed daily amount
    
    # Payout configuration
    @property
    def HC_TO_KZ_RATE(self) -> float:
        # Default: 20
        return remote_config_manager.get_value("HC_TO_KZ_RATE", 20.0, float)

    @property
    def PAYOUT_CONVERSION_RATE(self) -> float:
        return self.HC_TO_KZ_RATE
    MINIMUM_PAYOUT_HC: int = 10000  # Minimum HC required for payout (10,000 HC = 1,000 Kwanza)
    MAXIMUM_PAYOUT_HC: int = 30000  # Maximum HC allowed per payout (30,000 HC = 3,000 Kwanza)
    
    # Redis configuration for rate limiting
    REDIS_URL: str = "redis://localhost:6379/0"
    
    @property
    def LAND_INCOME_PER_SECOND(self) -> float:
        """Calculate land income per second from daily income"""
        return self.LAND_INCOME_PER_DAY / (24 * 3600)

    class Config:
        env_file = ".env"

settings = Settings()

# Export commonly used values for admin module
JWT_SECRET_KEY = settings.SECRET_KEY
JWT_ALGORITHM = settings.ALGORITHM