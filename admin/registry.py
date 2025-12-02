# admin/registry.py
from typing import Dict, Type, Any, List, Optional, get_origin, get_args, Union, Annotated
from datetime import datetime, date
from beanie import Document, Indexed
from pydantic import BaseModel
from bson import ObjectId
import json
import typing


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
        default_value: Any = None,
        is_safe_to_edit: bool = True,
        is_system_field: bool = False
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
        self.is_safe_to_edit = is_safe_to_edit
        self.is_system_field = is_system_field
    
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
            
            # Determine if this field is safe to edit
            is_safe_to_edit = cls._is_field_safe_to_edit(field_name, field_type)
            is_system_field = cls._is_system_field(field_name)
            
            # Handle special fields - mark internal/system fields as readonly
            internal_fields = ['id', 'createdAt', 'revision_id', '_id', '__v', 'updated_at']
            is_readonly = field_name in config.readonly_fields or field_name in internal_fields or is_system_field or not is_safe_to_edit
            
            default_value = cls._get_field_default(field_info_obj)
            
            # Create FieldInfo with smart widget detection and safety classification
            field_info[field_name] = FieldInfo(
                field_name=field_name,
                field_type=field_type,
                is_required=is_required,
                is_readonly=is_readonly,
                default_value=default_value,
                widget=cls._determine_widget(field_type, field_name),
                help_text=cls._generate_help_text(field_type, field_name, is_safe_to_edit),
                is_safe_to_edit=is_safe_to_edit,
                is_system_field=is_system_field
            )
        
        return field_info
    
    @classmethod
    def _extract_field_type(cls, field_info_obj) -> Type:
        """Extract the actual field type from Pydantic FieldInfo."""
        # Handle both Pydantic v1 and v2
        extracted_type = None
        if hasattr(field_info_obj, 'annotation'):
            extracted_type = field_info_obj.annotation
        elif hasattr(field_info_obj, 'type_'):
            extracted_type = field_info_obj.type_
        elif hasattr(field_info_obj, 'outer_type_'):
            extracted_type = field_info_obj.outer_type_
        else:
            return str
        
        # Handle both old Indexed(type) and new Annotated[type, Indexed()] approaches
        if extracted_type:
            # Method 1: New Annotated[type, Indexed()] approach (recommended)
            origin_type = typing.get_origin(extracted_type)
            if origin_type is not None:
                # Check if this is an Annotated type
                if origin_type is Annotated or str(origin_type) == 'typing.Annotated':
                    type_args = typing.get_args(extracted_type)
                    if type_args:
                        # First argument is the actual type (int, str, etc.)
                        actual_type = type_args[0]
                        print(f"Debug: Extracted {actual_type} from Annotated field")
                        return actual_type
            
            # Method 2: Old Indexed(type) approach (legacy support)
            if 'Indexed' in str(extracted_type):
                try:
                    if hasattr(extracted_type, '__bases__') and extracted_type.__bases__:
                        # The first base class is the actual type (int, str, etc.)
                        inner_type = extracted_type.__bases__[0]
                        if inner_type != object:  # Skip generic object base
                            print(f"Debug: Extracted {inner_type} from legacy Indexed field")
                            return inner_type
                    
                    # Fallback: Try to extract from string representation
                    type_str = str(extracted_type)
                    if 'int' in type_str.lower():
                        return int
                    elif 'str' in type_str.lower():
                        return str
                    elif 'float' in type_str.lower():
                        return float
                    elif 'bool' in type_str.lower():
                        return bool
                except Exception as e:
                    print(f"Warning: Failed to extract type from legacy Indexed field: {e}")
                    # Fallback based on common patterns
                    return str
        
        return extracted_type
    
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
        
        # Handle EmailStr type specifically
        elif 'EmailStr' in str(field_type) or 'email' in field_name.lower():
            return 'email'
        
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
    def _is_field_safe_to_edit(cls, field_name: str, field_type: Type) -> bool:
        """Determine if a field is safe to edit in admin panel.
        
        PRACTICAL SAFETY: Allow editing of fields that won't cause data corruption.
        Exclude only dangerous types that can break data integrity.
        """
        # System/internal fields are never safe to edit
        if cls._is_system_field(field_name):
            return False
        
        # Get origin type for generic types
        origin_type = get_origin(field_type)
        
        # Safe primitive and simple types
        safe_types = {
            str, int, float, bool,
            'str', 'int', 'float', 'bool', 
            '<class \'str\'>', '<class \'int\'>', '<class \'float\'>', '<class \'bool\'>'
        }
        
        # Check if it's a basic safe type
        if field_type in safe_types or str(field_type) in safe_types:
            return True
        
        # Handle EmailStr as safe (it's essentially a string)
        if 'EmailStr' in str(field_type):
            return True
        
        # DANGEROUS TYPES that cause corruption - exclude these
        dangerous_patterns = [
            'datetime', 'date',  # Time-based fields can break business logic
            'PydanticObjectId', 'ObjectId',  # Database IDs should not be manually edited
        ]
        
        type_str = str(field_type).lower()
        for dangerous in dangerous_patterns:
            if dangerous.lower() in type_str:
                return False
        
        # Handle Optional[SafeType] - check the inner type
        if origin_type is Union or 'Optional' in str(field_type):
            type_args = get_args(field_type)
            non_none_args = [arg for arg in type_args if arg != type(None)]
            if len(non_none_args) == 1:
                return cls._is_field_safe_to_edit(field_name, non_none_args[0])
        
        # Handle Annotated[SafeType, ...] - check the inner type
        if origin_type is Annotated or str(origin_type) == 'typing.Annotated':
            type_args = get_args(field_type)
            if type_args:
                return cls._is_field_safe_to_edit(field_name, type_args[0])
        
        # Handle List types - check if they contain simple types
        if origin_type == list or 'List' in str(field_type):
            type_args = get_args(field_type)
            if type_args:
                # Allow List[str], List[int], List[float], List[bool]
                inner_type = type_args[0]
                if inner_type in {str, int, float, bool} or str(inner_type) in {'str', 'int', 'float', 'bool'}:
                    return True
            # If no type args or unknown inner type, allow it (user responsibility)
            return True
        
        # Handle Dict types - check if they contain simple types
        if origin_type == dict or 'Dict' in str(field_type):
            type_args = get_args(field_type)
            if len(type_args) >= 2:
                key_type, value_type = type_args[0], type_args[1]
                # Allow Dict[str, simple_type] patterns
                simple_types = {str, int, float, bool}
                if (key_type in simple_types or str(key_type) in {'str', 'int', 'float', 'bool'}) and \
                   (value_type in simple_types or str(value_type) in {'str', 'int', 'float', 'bool'} or 'datetime' not in str(value_type).lower()):
                    return True
            # If no type args, allow it (user responsibility)
            return True
        
        # Allow most other types unless they're clearly dangerous
        # This gives users flexibility while protecting against known corruption sources
        return True
    
    @classmethod
    def _is_system_field(cls, field_name: str) -> bool:
        """Check if field is a system/internal field that should never be edited."""
        system_fields = {
            'id', '_id', 'createdAt', 'updated_at', 'revision_id', '__v',
            'hashed_password', 'password_hash', 'salt',
            'created_at', 'last_login', 'last_modified',
            'session_token', 'access_token', 'refresh_token'
        }
        
        # Check exact matches and patterns
        if field_name in system_fields:
            return True
        
        # Check patterns
        if (field_name.endswith('_id') and field_name != 'user_id' and field_name != 'national_id') or \
           field_name.startswith('_') or \
           'password' in field_name.lower() or \
           'token' in field_name.lower() or \
           'hash' in field_name.lower():
            return True
        
        return False
    
    @classmethod
    def _generate_help_text(cls, field_type: Type, field_name: str, is_safe_to_edit: bool = True) -> str:
        """Generate helpful text for complex field types."""
        # Add safety warning for unsafe fields
        if not is_safe_to_edit:
            safety_warning = "⚠️ READ-ONLY: Complex field type - editing disabled to prevent data corruption. "
        else:
            safety_warning = ""
        
        origin_type = get_origin(field_type)
        
        if origin_type == list or 'List' in str(field_type):
            args = get_args(field_type)
            if args and hasattr(args[0], '__name__'):
                return f"{safety_warning}JSON array of {args[0].__name__} objects. Example: [{{'key': 'value'}}]"
            return f"{safety_warning}JSON array. Example: [{'key': 'value'}]"
        
        elif origin_type == dict or 'Dict' in str(field_type):
            args = get_args(field_type)
            if len(args) >= 2:
                key_type = args[0].__name__ if hasattr(args[0], '__name__') else str(args[0])
                val_type = args[1].__name__ if hasattr(args[1], '__name__') else str(args[1])
                return f"{safety_warning}JSON object with {key_type} keys and {val_type} values. Example: {{'key': 'value'}}"
            return f"{safety_warning}JSON object. Example: {'key': 'value'}"
        
        elif field_type in [datetime, date] or 'datetime' in str(field_type).lower() or 'date' in str(field_type).lower():
            return f"{safety_warning}Date and time fields are read-only to prevent business logic corruption"
        
        elif 'password' in field_name.lower():
            return f"{safety_warning}Password will be hashed automatically"
        
        elif cls._is_system_field(field_name):
            return f"{safety_warning}System field - automatically managed."
        
        return safety_warning.rstrip()
    

    
    @classmethod
    def get_editable_fields(cls, model_name: str) -> Dict[str, FieldInfo]:
        """Get only the fields that are safe to edit in the admin panel."""
        all_fields = cls.get_field_info(model_name)
        return {
            name: field_info for name, field_info in all_fields.items()
            if field_info.is_safe_to_edit and not field_info.is_readonly and not field_info.is_system_field
        }
    
    @classmethod
    def get_readonly_fields(cls, model_name: str) -> Dict[str, FieldInfo]:
        """Get fields that should be displayed as read-only."""
        all_fields = cls.get_field_info(model_name)
        return {
            name: field_info for name, field_info in all_fields.items()
            if not field_info.is_safe_to_edit or field_info.is_readonly or field_info.is_system_field
        }
    
    @classmethod
    def process_form_data(cls, model_name: str, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Safely process form data - only editable fields are processed."""
        model = cls.get_model(model_name)
        if not model:
            return {}
        
        # CRITICAL: Only process fields that are safe to edit
        editable_fields = cls.get_editable_fields(model_name)
        processed_data = {}
        
        print(f"[SAFE EDIT] Processing {model_name} - {len(editable_fields)} editable fields out of {len(cls.get_field_info(model_name))} total")
        
        # Get the model's Pydantic schema for validation
        model_fields = getattr(model, 'model_fields', {}) or getattr(model, '__fields__', {})
        
        for field_name, field_info_obj in editable_fields.items():
            if field_name in form_data:
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
                        print(f"[SAFE EDIT] Processed safe field: {field_name} = {converted_value}")
                        
                except Exception as e:
                    print(f"[SAFE EDIT] Warning: Failed to convert safe field '{field_name}' with value '{raw_value}': {e}")
                    # Skip problematic fields to prevent data corruption
                    continue
        
        # Log any fields that were ignored for security
        ignored_fields = set(form_data.keys()) - set(editable_fields.keys())
        if ignored_fields:
            print(f"[SAFE EDIT] Ignored unsafe/readonly fields: {', '.join(ignored_fields)}")
        
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
        
        # Basic type conversions - FIXED: Separate int and str checks
        if field_type == int or str(field_type) in ['int', '<class \'int\'>']:
            try:
                return int(value) if value else 0
            except (ValueError, TypeError):
                print(f"Warning: Failed to convert '{value}' to int for field '{field_name}'")
                return 0
        
        elif field_type == float or str(field_type) in ['float', '<class \'float\'>']:
            try:
                return float(value) if value else 0.0
            except (ValueError, TypeError):
                print(f"Warning: Failed to convert '{value}' to float for field '{field_name}'")
                return 0.0
        
        elif field_type == bool or str(field_type) in ['bool', '<class \'bool\'>']:
            if isinstance(value, str):
                return value.lower() in ['true', '1', 'on', 'yes']
            return bool(value)
        
        elif field_type == str or str(field_type) in ['str', '<class \'str\'>']:
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
    """Automatically register models with safe field configurations."""
    from data.models.models import User, Quiz, LandTile, Payout
    from admin.models import AdminUser
    
    # Register User model with STRICT SAFETY CONTROLS
    AdminRegistry.register(
        User,
        AdminModelConfig(
            User,
            verbose_name="User",
            verbose_name_plural="Users",
            list_display=["username", "email", "hc_balance", "level", "current_hustle"],
            search_fields=["username", "email"],
            # Force readonly for dangerous fields - automatic safety system will handle the rest
            readonly_fields=[
                "id", "createdAt", "hashed_password", "inventory", "task_cooldowns", 
                "last_check_in_date", "last_tap_reset_date", "last_land_claim_at"
            ],
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
    
    # Register LandTile model with SAFETY CONTROLS
    AdminRegistry.register(
        LandTile,
        AdminModelConfig(
            LandTile,
            verbose_name="Land Tile",
            verbose_name_plural="Land Tiles",
            list_display=["h3_index", "owner_id", "purchase_price", "purchased_at"],
            # System should only allow editing of purchase_price - other fields are system managed
            readonly_fields=["id", "purchased_at", "last_income_payout_at", "owner_id", "h3_index"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register AdminUser model with MAXIMUM SECURITY
    AdminRegistry.register(
        AdminUser,
        AdminModelConfig(
            AdminUser,
            verbose_name="Admin User",
            verbose_name_plural="Admin Users",
            list_display=["username", "email", "is_superuser", "is_active", "created_at"],
            # Critical: Never allow editing of password hash or system timestamps
            readonly_fields=["id", "created_at", "last_login", "hashed_password"],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
    
    # Register Payout model with STRICT FINANCIAL SAFETY
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
            # CRITICAL: Financial data should be readonly - only status and admin fields can be edited
            readonly_fields=[
                "id", "created_at", "updated_at", "user_id", "amount_hc", 
                "amount_kwanza", "conversion_rate", "payout_method",
                "phone_number", "full_name", "national_id", "bank_iban", "bank_name"
            ],
            exclude_fields=["revision_id", "_id", "__v"]
        )
    )
