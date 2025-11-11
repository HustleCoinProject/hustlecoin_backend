# HustleCoin Admin Panel

A comprehensive Django-style admin panel for the HustleCoin backend, built with FastAPI and server-side rendering.

## Features

- 🔐 **Secure Authentication**: JWT-based authentication with cookie sessions
- 👥 **User Management**: Create, edit, and manage admin users with superuser permissions
- 📊 **Database Management**: View, create, edit, and delete records from all collections
- 🎨 **Modern UI**: Beautiful, responsive interface with Bootstrap 5
- 🔧 **Auto-Discovery**: Automatically discovers and registers database models
- 📱 **Mobile Friendly**: Responsive design that works on all devices
- ⚙️ **Customizable**: Easy to configure field display, validation, and permissions

## Quick Start

### 1. Create an Admin User

Use the CLI utility to create your first admin user:

```bash
# Create a regular admin user
python admin_cli.py create-admin --username admin --email admin@example.com

# Create a superuser (recommended for first user)
python admin_cli.py create-admin --username admin --email admin@example.com --superuser
```

### 2. Start the Server

```bash
uvicorn app:app --reload
```

### 3. Access the Admin Panel

Visit `http://localhost:8000/admin/` and login with your admin credentials.

## CLI Commands

The admin panel includes a command-line utility for managing admin users:

### Create Admin User
```bash
python admin_cli.py create-admin --username <username> --email <email> [--password <password>] [--superuser]
```

### List Admin Users
```bash
python admin_cli.py list-admins
```

### Change Password
```bash
python admin_cli.py change-password --username <username> [--password <new_password>]
```

## Configuration

### Registering Models

Models are automatically registered in `admin/registry.py`. You can customize how they appear in the admin:

```python
from admin.registry import AdminRegistry, AdminModelConfig
from your_app.models import YourModel

# Register with custom configuration
AdminRegistry.register(
    YourModel,
    AdminModelConfig(
        YourModel,
        verbose_name="Your Model",
        verbose_name_plural="Your Models",
        list_display=["field1", "field2", "field3"],
        search_fields=["field1", "field2"],
        readonly_fields=["id", "created_at"],
        exclude_fields=["sensitive_field"]
    )
)
```

### Field Types

The admin panel automatically handles different field types:

- **Text Fields**: String inputs with validation
- **Number Fields**: Integer and float inputs
- **Boolean Fields**: Checkboxes
- **DateTime Fields**: Date/time pickers
- **JSON Fields**: Textarea with JSON validation
- **List Fields**: Textarea with JSON array format

### Permissions

- **Regular Admin**: Can view and edit collections
- **Superuser**: Full access to all features including user management

## Architecture

### Modular Design

The admin panel is designed as a completely separate module that can be removed without affecting the main application:

```
admin/
├── __init__.py          # Module exports
├── models.py            # Admin user model
├── auth.py              # Authentication logic
├── crud.py              # Database operations
├── registry.py          # Model registration system
├── routes.py            # Web routes and views
├── templates/           # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── collection_list.html
│   └── document_form.html
└── static/              # CSS and JavaScript
    ├── css/admin.css
    └── js/admin.js
```

### Security Features

- JWT authentication with secure cookie storage
- Password hashing with bcrypt
- CSRF protection (via form tokens)
- Session timeout (30 minutes default)
- Input validation and sanitization

### Database Independence

The admin panel uses the same database connection as your main application but maintains its own collection for admin users. It can be completely removed without affecting your existing data.

## Customization

### Templates

All templates extend `base.html` and can be customized:

- `login.html`: Login page
- `dashboard.html`: Main dashboard
- `collection_list.html`: List view for collections
- `document_form.html`: Create/edit forms

### Styling

The admin panel uses Bootstrap 5 with custom CSS in `static/css/admin.css`. You can override styles or add your own themes.

### Field Widgets

Custom field widgets can be defined in the `FieldInfo` class:

```python
field_overrides = {
    "description": FieldInfo(
        field_name="description",
        field_type=str,
        widget="textarea",
        help_text="Enter a detailed description"
    )
}
```

## Troubleshooting

### Common Issues

1. **Admin user creation fails**: Make sure the database is running and accessible
2. **Login redirects loop**: Check JWT_SECRET_KEY is set in your environment
3. **Static files not loading**: Ensure the static files mount is configured in `app.py`
4. **Models not appearing**: Check that `auto_register_models()` is called on startup

### Debug Mode

Enable debug logging in your FastAPI app to see detailed error messages:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security Considerations

1. Always use HTTPS in production
2. Set secure cookie flags in production
3. Use strong passwords for admin users
4. Regularly update admin user passwords
5. Monitor admin access logs
6. Limit admin access to trusted networks if possible

## Contributing

The admin panel is designed to be extensible. You can:

1. Add new field types by extending `FieldInfo`
2. Create custom widgets by modifying templates
3. Add new permissions by extending the auth system
4. Customize the UI by modifying CSS and templates

## License

This admin panel is part of the HustleCoin backend project.
