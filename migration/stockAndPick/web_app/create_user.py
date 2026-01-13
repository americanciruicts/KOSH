#!/usr/bin/env python3
"""
Script to create new users for KOSH Inventory System
Usage: python3 create_user.py
"""

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor
import getpass

def create_user():
    """Interactive script to create a new user."""
    print("\n=== KOSH Inventory System - Create User ===\n")

    # Get user details
    username = input("Enter username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        return

    full_name = input("Enter full name (optional): ").strip() or username
    email = input("Enter email (optional): ").strip() or None

    # Get password
    password = getpass.getpass("Enter password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("Error: Passwords do not match")
        return

    if len(password) < 6:
        print("Error: Password must be at least 6 characters")
        return

    # Get role
    print("\nAvailable roles:")
    print("1. USER - Standard user (can view and manage inventory)")
    print("2. ADMIN - Administrator (full access)")
    role_choice = input("Select role (1 or 2): ").strip()
    role = 'ADMIN' if role_choice == '2' else 'USER'

    # ITAR authorization
    itar_choice = input("ITAR authorized? (y/n): ").strip().lower()
    itar_authorized = itar_choice == 'y'

    # Hash password
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Connect to database
    try:
        conn = psycopg2.connect(
            host='aci-database',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Insert user
        cursor.execute("""
            INSERT INTO pcb_inventory."tblUsers"
            (username, password_hash, full_name, email, role, itar_authorized)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, username, full_name, role
        """, (username, password_hash, full_name, email, role, itar_authorized))

        user = cursor.fetchone()
        conn.commit()

        print("\n✅ User created successfully!")
        print(f"ID: {user['id']}")
        print(f"Username: {user['username']}")
        print(f"Full Name: {user['full_name']}")
        print(f"Role: {user['role']}")
        print(f"ITAR Authorized: {itar_authorized}")

        cursor.close()
        conn.close()

    except psycopg2.IntegrityError:
        print(f"\n❌ Error: Username '{username}' already exists")
    except Exception as e:
        print(f"\n❌ Error creating user: {e}")

if __name__ == '__main__':
    create_user()
