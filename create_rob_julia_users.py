#!/usr/bin/env python3
"""
Script to create users Rob and Julia for KOSH Inventory System
"""

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

def create_user(conn, username, full_name, password, role='USER', itar_authorized=True, email=None):
    """Create a user in the database."""
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Insert user
        cursor.execute("""
            INSERT INTO pcb_inventory."tblUsers"
            (username, password_hash, full_name, email, role, itar_authorized)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, username, full_name, role, itar_authorized
        """, (username, password_hash, full_name, email, role, itar_authorized))

        user = cursor.fetchone()
        conn.commit()

        print(f"✅ User created successfully!")
        print(f"   Username: {user['username']}")
        print(f"   Full Name: {user['full_name']}")
        print(f"   Role: {user['role']}")
        print(f"   ITAR Authorized: {user['itar_authorized']}")
        print()

        cursor.close()
        return True

    except psycopg2.IntegrityError:
        conn.rollback()
        print(f"⚠️  Username '{username}' already exists - skipping")
        print()
        return False
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creating user '{username}': {e}")
        print()
        return False

def main():
    print("\n=== Creating Users: Rob and Julia ===\n")

    # Connect to database
    try:
        conn = psycopg2.connect(
            host='aci-database',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )

        # Create Rob
        print("Creating user: Rob")
        create_user(
            conn=conn,
            username='rob',
            full_name='Rob',
            password='rob123',  # Default password, user should change
            role='USER',
            itar_authorized=True,
            email='rob@aci.local'
        )

        # Create Julia
        print("Creating user: Julia")
        create_user(
            conn=conn,
            username='julia',
            full_name='Julia',
            password='julia123',  # Default password, user should change
            role='USER',
            itar_authorized=True,
            email='julia@aci.local'
        )

        conn.close()
        print("✅ Done! Both users have been created.")
        print("\nLogin credentials:")
        print("  Rob:   username='rob'   password='rob123'")
        print("  Julia: username='julia' password='julia123'")
        print("\n⚠️  Note: Users should change their passwords after first login")

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        print("\nTroubleshooting:")
        print("  - Make sure the database container is running")
        print("  - Check that port 5434 is accessible")
        return 1

    return 0

if __name__ == '__main__':
    exit(main())
