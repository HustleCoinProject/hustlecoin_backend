# admin/registry.py
from typing import Dict, Type, Any, List, Optional, get_origin, get_args, Union
from datetime import datetime, date
from beanie import Document
from pydantic import BaseModel
from bson import ObjectId
import json


class FieldInfo:
    """Information about a model field for admin interface."""
    
    def __init__(
        self,
        field_name: str,
        field_type: Type,
        verbose_name: Optional[str] = None,
        help_text: Optional[str] = None,
        is_required: bool = False,
        choices: Optional[List[tuple]] = None,
        widget: Optional[str] = None,
        is_readonly: bool = False,
        is_hidden: bool = False,
        default_value: Any = None
    ):
        self.field_name = field_name
        self.field_type = field_type
        self.verbose_name = verbose_name or field_name.replace('_', ' ').title()
        self.help_text = help_text
        self.is_required = is_required
        self.choices = choices
        self.widget = widget or self._get_default_widget()
        self.is_readonly = is_readonly
        self.is_hidden = is_hidden
        self.default_value = default_value
    
    def _get_default_widget(self) -> str:
        """Get default widget based on field type."""
        if self.field_type == str:
            return "text"
        elif self.field_type in [int, float]:
            return "number"
        elif self.field_type == bool:
            return "checkbox"
        elif self.field_type in [datetime, date]:
            return "datetime"
        elif self.field_type == list:
            return "textarea"
        elif self.field_type == dict:
            return "json"
        else:
            return "text"


class AdminModelConfig:
    """Configuration for a model in admin interface."""
    
    def __init__(
        self,
        model_class: Type[Document],
        verbose_name: Optional[str] = None,
        verbose_name_plural: Optional[str] = None,
        list_display: Optional[List[str]] = None,
        list_filter: Optional[List[str]] = None,
        search_fields: Optional[List[str]] = None,
        ordering: Optional[List[str]] = None,
        readonly_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        field_overrides: Optional[Dict[str, FieldInfo]] = None
    ):
        self.model_class = model_class
        self.verbose_name = verbose_name or model_class.__name__
        self.verbose_name_plural = verbose_name_plural or f"{self.verbose_name}s"
        self.list_display = list_display or ["id"]
        self.list_filter = list_filter or []
        self.search_fields = search_fields or []
        self.ordering = ordering or []
        self.readonly_fields = readonly_fields or []
        self.exclude_fields = exclude_fields or []
        self.field_overrides = field_overrides or {}


class AdminRegistry:
    """Registry for admin models and their configurations."""
    
    _registered_models: Dict[str, Type[Document]] = {}
    _model_configs: Dict[str, AdminModelConfig] = {}
    
    @classmethod
    def register(
        cls,
        model_class: Type[Document],
        config: Optional[AdminModelConfig] = None
    ):
        """Register a model with the admin interface."""
        model_name = model_class.__name__.lower()
        cls._registered_models[model_name] = model_class
        cls._model_configs[model_name] = config or AdminModelConfig(model_class)
    
    @classmethod
    def get_registered_models(cls) -> Dict[str, Type[Document]]:
        """Get all registered models."""
        return cls._registered_models.copy()
    
    @classmethod
    def get_model(cls, model_name: str) -> Optional[Type[Document]]:
        """Get a registered model by name."""
        return cls._registered_models.get(model_name.lower())
    
    @classmethod
    def get_config(cls, model_name: str) -> Optional[AdminModelConfig]:
        """Get model configuration."""
        return cls._model_configs.get(model_name.lower())
    
    @classmethod
    def get_verbose_name(cls, model_name: str) -> str:
        """Get verbose name for a model."""
        config = cls.get_config(model_name)
        return config.verbose_name if config else model_name.title()
    
    @classmethod
    def get_field_info(cls, model_name: str) -> Dict[str, FieldInfo]:
        """Get field information for a model using Pydantic model introspection."""
        model = cls.get_model(model_name)
        config = cls.get_config(model_name)
        
        if not model or not config:
            return {}
        
        field_info = {}
        
        # Use Pydantic model fields for accurate type information
        model_fields = getattr(model, 'model_fields', {}) or getattr(model, '__fields__', {})
        
        for field_name, field_info_obj in model_fields.items():
            if field_name in config.exclude_fields:
                continue
            
            # Check for field overrides
            if field_name in config.field_overrides:
                field_info[field_name] = config.field_overrides[field_name]
                continue
            
            # Extract field information from Pydantic FieldInfo
            field_type = cls._extract_field_type(field_info_obj)
            is_required = cls._is_field_required_from_field_info(field_info_obj)
            
            # Handle special fields - mark internal/system fields as readonly
            internal_fields = ['id', 'createdAt', 'revision_id', '_id', '__v', 'updated_at']
            is_readonly = field_name in config.readonly_fields or field_name in internal_fields
            default_value = cls._get_field_default(field_info_obj)
            
            # Create FieldInfo with smart widget detection
            field_info[field_name] = FieldInfo(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                is_readonly=is_readonly,
                default_value=default_value,
                widget=cls._determine_widget(field_type, field_name),
                help_text=cls._generate_help_text(field_type, field_name)
            )
        
        return field_info
    
    @classmethod
    def _extract_field_type(cls, field_info_obj) -> Type:
        """Extract the actual field type from Pydantic FieldInfo."""
        # Handle both Pydantic v1 and v2
        if hasattr(field_info_obj, 'annotation'):
            return field_info_obj.annotation
        elif hasattr(field_info_obj, 'type_'):
            return field_info_obj.type_
        elif hasattr(field_info_obj, 'outer_type_'):
            return field_info_obj.outer_type_
        else:
            return str
    
    @classmethod
    def _is_field_required_from_field_info(cls, field_info_obj) -> bool:
        """Check if field is required from Pydantic FieldInfo."""
        if hasattr(field_info_obj, 'is_required'):
            return field_info_obj.is_required()
        elif hasattr(field_info_obj, 'required'):
            return field_info_obj.required
        elif hasattr(field_info_obj, 'default'):
            return field_info_obj.default is ... or field_info_obj.default is Ellipsis
        return False
    
    @classmethod 
    def _get_field_default(cls, field_info_obj):
        """Get field default value from Pydantic FieldInfo."""
        if hasattr(field_info_obj, 'default'):
            default = field_info_obj.default
            if default is not ... and default is not Ellipsis:
                return default
        return None
    
    @classmethod
    def _determine_widget(cls, field_type: Type, field_name: str) -> str:
        """Intelligently determine the widget type based on field type and name."""
        # Get the origin type for generic types
        origin_type = get_origin(field_type)
        
        # Handle primitive types
        if field_type == str or field_type == 'str':
            if 'password' in field_name.lower():
                return 'password'
            elif 'email' in field_name.lower():
                return 'email'
            elif 'url' in field_name.lower() or 'link' in field_name.lower():
                return 'url'
            elif 'description' in field_name.lower() or 'text' in field_name.lower() or 'content' in field_name.lower():
                return 'textarea'
            else:
                return 'text'
        
        elif field_type in [int, float] or str(field_type) in ['int', 'float']:
            return 'number'
        
        elif field_type == bool or str(field_type) == 'bool':
            return 'checkbox'
        
        elif field_type in [datetime, date] or str(field_type) in ['datetime', 'date']:
            return 'datetime'
        
        # Handle generic types (List, Dict, Optional, etc.)
        elif origin_type is not None:
            if origin_type == list or str(origin_type) == 'list':
                return 'json_array'
            elif origin_type == dict or str(origin_type) == 'dict':
                return 'json_object'
            elif origin_type == tuple:
                return 'json_array'
            else:
                return 'json'
        
        # Handle string representations of types (fallback)
        elif 'List' in str(field_type) or 'list' in str(field_type):
            return 'json_array'
        elif 'Dict' in str(field_type) or 'dict' in str(field_type):
            return 'json_object'
        elif 'Optional' in str(field_type):
            # Extract the inner type for Optional
            args = get_args(field_type)
            if args:
                return cls._determine_widget(args[0], field_name)
            return 'text'
        
        # Default fallback
        return 'text'
    
    @classmethod
    def _generate_help_text(cls, field_type: Type, field_name: str) -> str:
        """Generate helpful text for complex field types."""
        origin_type = get_origin(field_type)
        
        if origin_type == list or 'List' in str(field_type):
            args = get_args(field_type)
            if args and hasattr(args[0], '__name__'):
                return f"JSON array of {args[0].__name__} objects. Example: [{{'key': 'value'}}]"
            return "JSON array. Example: [{'key': 'value'}]"
        
        elif origin_type == dict or 'Dict' in str(field_type):
            args = get_args(field_type)
            if len(args) >= 2:
                key_type = args[0].__name__ if hasattr(args[0], '__name__') else str(args[0])
                val_type = args[1].__name__ if hasattr(args[1], '__name__') else str(args[1])
                return f"JSON object with {key_type} keys and {val_type} values. Example: {{'key': 'value'}}"
            return "JSON object. Example: {'key': 'value'}"
        
        elif field_type in [datetime, date]:
            return "Date and time in ISO format (YYYY-MM-DDTHH:MM:SS)"
        
        elif 'password' in field_name.lower():
            return "Password will be hashed automatically"
        
        return ""
    

    
    @classmethod
    def process_form_data(cls, model_name: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Intelligently process form data using Pydantic model introspection."""
        model = cls.get_model(model_name)
        field_info = cls.get_field_info(model_name)
        
        if not model:
            return {}
        
        processed_data = {}
        
        # Get the model's Pydantic schema for validation
        model_fields = getattr(model, 'model_fields', {}) or getattr(model, '__fields__', {})
        
        for field_name, field_info_obj in field_info.items():
            if field_name in form_data and not field_info_obj.is_readonly:
                raw_value = form_data[field_name]
                
                # Skip empty values for optional fields
                if not raw_value and not field_info_obj.is_required:
                    continue
                
                try:
                    # Use the model's field information for intelligent conversion
                    pydantic_field = model_fields.get(field_name)
                    converted_value = cls._smart_convert_value(
                        field_name, raw_value, field_info_obj.field_type, pydantic_field
                    )
                    
                    if converted_value is not None:
                        processed_data[field_name] = converted_value
                        
                except Exception as e:
                    print(f"Warning: Failed to convert field '{field_name}' with value '{raw_value}': {e}")
                    # Skip problematic fields to prevent data corruption
                    continue
        
        return processed_data
    
    @classmethod
    def _smart_convert_value(cls, field_name: str, value: Any, field_type: Type, pydantic_field) -> Any:
        """Intelligently convert form values using type information."""
        # Handle empty values
        if value is None or value == "":
            return None
        
        # Get origin type for generic types (List, Dict, Optional, etc.)
        origin_type = get_origin(field_type)
        type_args = get_args(field_type)
        
        # Handle Optional types
        if origin_type is Union or 'Optional' in str(field_type):
            # For Optional[T], get the non-None type
            non_none_args = [arg for arg in type_args if arg != type(None)]
            if non_none_args:
                return cls._smart_convert_value(field_name, value, non_none_args[0], pydantic_field)
        
        # Basic type conversions
        if field_type in [int, str] or str(field_type) in ['int', '<class \'int\'>']:
            return int(value) if value else 0
        
        elif field_type in [float] or str(field_type) in ['float', '<class \'float\'>']:
            return float(value) if value else 0.0
        
        elif field_type in [bool] or str(field_type) in ['bool', '<class \'bool\'>']:
            if isinstance(value, str):
                return value.lower() in ['true', '1', 'on', 'yes']
            return bool(value)
        
        elif field_type in [str] or str(field_type) in ['str', '<class \'str\'>']:
            return str(value)
        
        elif field_type in [datetime] or 'datetime' in str(field_type):
            if isinstance(value, str) and value:
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    return datetime.strptime(value, '%Y-%m-%dT%H:%M')
            return value
        
        elif field_type in [date] or 'date' in str(field_type):
            if isinstance(value, str) and value:
                return date.fromisoformat(value)
            return value
        
        # Handle List types
        elif origin_type == list or 'List' in str(field_type):
            if isinstance(value, str):
                try:
                    parsed_list = json.loads(value) if value else []
                    
                    # If we have type args, convert list items
                    if type_args and len(type_args) > 0:
                        item_type = type_args[0]
                        converted_list = []
                        
                        for item in parsed_list:
                            try:
                                # For complex objects like InventoryItem, create instance
                                if hasattr(item_type, '__fields__') or hasattr(item_type, 'model_fields'):
                                    if isinstance(item, dict):
                                        converted_list.append(item_type(**item))
                                    else:
                                        converted_list.append(item)
                                else:
                                    converted_list.append(item)
                            except Exception as e:
                                print(f"Warning: Failed to convert list item for {field_name}: {e}")
                                # Include as-is rather than skip
                                converted_list.append(item)
                        
                        return converted_list
                    
                    return parsed_list
                except json.JSONDecodeError:
                    print(f"Warning: Invalid JSON for list field '{field_name}': {value}")
                    return []
            return value if isinstance(value, list) else []
        
        # Handle Dict types  
        elif origin_type == dict or 'Dict' in str(field_type):
            if isinstance(value, str):
                try:
                    parsed_dict = json.loads(value) if value else {}
                    
                    # Handle typed dictionaries like Dict[str, datetime]
                    if len(type_args) >= 2:
                        key_type, value_type = type_args[0], type_args[1]
                        converted_dict = {}
                        
                        for k, v in parsed_dict.items():
                            try:
                                # Convert key
                                converted_key = cls._smart_convert_value(f"{field_name}_key", k, key_type, None)
                                # Convert value
                                converted_value = cls._smart_convert_value(f"{field_name}_value", v, value_type, None)
                                converted_dict[converted_key] = converted_value
                            except Exception as e:
                                print(f"Warning: Failed to convert dict item {k}:{v} for {field_name}: {e}")
                                # Include as-is rather than skip
                                converted_dict[k] = v
                        
                        return converted_dict
                    
                    return parsed_dict
                except json.JSONDecodeError:
                    print(f"Warning: Invalid JSON for dict field '{field_name}': {value}")
                    return {}
            return value if isinstance(value, dict) else {}
        
        # For other complex types, try JSON parsing
        elif isinstance(value, str) and (value.startswith('{') or value.startswith('[')):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        # Return as-is for unknown types
        return value


# Auto-register models from data.models
def auto_register_models():
    """Automatically register models from the data.models module."""
    from data.models.models import User, Quiz, LandTile, Payout
    from admin.models import AdminUser
    
    # Register User model
    AdminRegistry.register(
        User,
        AdminModelConfig(
            User,
            verbose_name="User",
            verbose_name_plural="Users",
            list_display=["username", "email", "hc_balance", "level", "current_hustle"],
            search_fields=["username", "email"],
            readonly_fields=["id", "createdAt", "hashed_password"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register Quiz model
    AdminRegistry.register(
        Quiz,
        AdminModelConfig(
            Quiz,
            verbose_name="Quiz",
            verbose_name_plural="Quizzes",
            list_display=["question_en", "correctAnswerIndex", "isActive"],
            readonly_fields=["id"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register LandTile model
    AdminRegistry.register(
        LandTile,
        AdminModelConfig(
            LandTile,
            verbose_name="Land Tile",
            verbose_name_plural="Land Tiles",
            list_display=["h3_index", "owner_id", "purchase_price", "purchased_at"],
            readonly_fields=["id", "purchased_at", "last_income_payout_at"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register AdminUser model
    AdminRegistry.register(
        AdminUser,
        AdminModelConfig(
            AdminUser,
            verbose_name="Admin User",
            verbose_name_plural="Admin Users",
            list_display=["username", "email", "is_superuser", "is_active", "created_at"],
            readonly_fields=["id", "created_at", "last_login", "hashed_password"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register Payout model
    AdminRegistry.register(
        Payout,
        AdminModelConfig(
            Payout,
            verbose_name="Payout",
            verbose_name_plural="Payouts",
            list_display=["user_id", "amount_kwanza", "payout_method", "status", "created_at"],
            list_filter=["status", "payout_method"],
            search_fields=["phone_number", "full_name", "bank_name"],
            ordering=["-created_at"],
            readonly_fields=["id", "created_at", "user_id", "amount_hc", "amount_kwanza", "conversion_rate"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
