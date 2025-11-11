#!/usr/bin/env python3
"""
Admin CLI utility for HustleCoin backend.
This script provides command-line interface for admin user management.

Usage:
    python admin_cli.py create-admin --username admin --email admin@example.com --password yourpassword [--superuser]
    python admin_cli.py list-admins
    python admin_cli.py change-password --username admin --password newpassword
"""

import asyncio
import argparse
import getpass
import sys
from core.database import init_db
from admin.crud import create_admin_user, list_admin_users, update_admin_password


async def create_admin_command(args):
    """Create a new admin user."""
    try:
        password = args.password
        if not password:
            password = getpass.getpass("Enter password: ")
            confirm_password = getpass.getpass("Confirm password: ")
            if password != confirm_password:
                print("❌ Passwords don't match!")
                return False
        
        admin_user = await create_admin_user(
            username=args.username,
            email=args.email,
            password=password,
            is_superuser=args.superuser
        )
        
        print(f"✅ Admin user '{admin_user.username}' created successfully!")
        print(f"   Email: {admin_user.email}")
        print(f"   Superuser: {'Yes' if admin_user.is_superuser else 'No'}")
        print(f"   Active: {'Yes' if admin_user.is_active else 'No'}")
        return True
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


async def list_admins_command(args):
    """List all admin users."""
    try:
        admins = await list_admin_users()
        
        if not admins:
            print("📝 No admin users found.")
            return True
        
        print(f"📋 Found {len(admins)} admin user(s):")
        print("-" * 80)
        print(f"{'Username':<20} {'Email':<30} {'Superuser':<10} {'Active':<8} {'Created'}")
        print("-" * 80)
        
        for admin in admins:
            print(f"{admin.username:<20} {admin.email:<30} {'Yes' if admin.is_superuser else 'No':<10} {'Yes' if admin.is_active else 'No':<8} {admin.created_at.strftime('%Y-%m-%d')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error listing admins: {e}")
        return False


async def change_password_command(args):
    """Change admin user password."""
    try:
        password = args.password
        if not password:
            password = getpass.getpass(f"Enter new password for '{args.username}': ")
            confirm_password = getpass.getpass("Confirm new password: ")
            if password != confirm_password:
                print("❌ Passwords don't match!")
                return False
        
        success = await update_admin_password(args.username, password)
        
        if success:
            print(f"✅ Password updated successfully for user '{args.username}'!")
            return True
        else:
            print(f"❌ Admin user '{args.username}' not found!")
            return False
            
    except Exception as e:
        print(f"❌ Error updating password: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="HustleCoin Admin CLI")
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Create admin command
    create_parser = subparsers.add_parser('create-admin', help='Create a new admin user')
    create_parser.add_argument('--username', required=True, help='Admin username')
    create_parser.add_argument('--email', required=True, help='Admin email')
    create_parser.add_argument('--password', help='Admin password (will prompt if not provided)')
    create_parser.add_argument('--superuser', action='store_true', help='Make this user a superuser')
    
    # List admins command
    list_parser = subparsers.add_parser('list-admins', help='List all admin users')
    
    # Change password command
    password_parser = subparsers.add_parser('change-password', help='Change admin user password')
    password_parser.add_argument('--username', required=True, help='Admin username')
    password_parser.add_argument('--password', help='New password (will prompt if not provided)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    async def run_command():
        # Initialize database connection
        print("🔄 Connecting to database...")
        await init_db()
        print("✅ Database connected!")
        
        if args.command == 'create-admin':
            success = await create_admin_command(args)
        elif args.command == 'list-admins':
            success = await list_admins_command(args)
        elif args.command == 'change-password':
            success = await change_password_command(args)
        else:
            print(f"❌ Unknown command: {args.command}")
            success = False
        
        if not success:
            sys.exit(1)
    
    # Run the async command
    asyncio.run(run_command())


if __name__ == "__main__":
    main()
