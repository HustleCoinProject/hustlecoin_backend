@echo off
REM HustleCoin Admin CLI Helper for Windows

echo.
echo ========================================
echo  HustleCoin Admin Panel CLI
echo ========================================
echo.

if "%1"=="" (
    echo Usage examples:
    echo   %0 create-admin username email [superuser]
    echo   %0 list-admins
    echo   %0 change-password username
    echo.
    echo Commands:
    echo   create-admin   - Create a new admin user
    echo   list-admins    - List all admin users  
    echo   change-password - Change admin password
    echo.
    goto :eof
)

if "%1"=="create-admin" (
    if "%3"=="" (
        echo Error: Username and email required
        echo Usage: %0 create-admin username email [superuser]
        goto :eof
    )
    
    if "%4"=="superuser" (
        echo Creating superuser admin...
        python admin_cli.py create-admin --username %2 --email %3 --superuser
    ) else (
        echo Creating regular admin...
        python admin_cli.py create-admin --username %2 --email %3
    )
    goto :eof
)

if "%1"=="list-admins" (
    echo Listing all admin users...
    python admin_cli.py list-admins
    goto :eof
)

if "%1"=="change-password" (
    if "%2"=="" (
        echo Error: Username required
        echo Usage: %0 change-password username
        goto :eof
    )
    
    echo Changing password for user: %2
    python admin_cli.py change-password --username %2
    goto :eof
)

echo Unknown command: %1
echo Use "%0" without arguments to see usage instructions.
