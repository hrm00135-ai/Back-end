"""
Super Admin Seed Script
=======================
Run this ONCE to create the Super Admin user via backend.
This is the ONLY way to create a Super Admin.

Usage:
    python scripts/seed_super_admin.py

Or with custom values:
    SUPER_ADMIN_EMAIL=admin@example.com \
    SUPER_ADMIN_PASSWORD=MySecure@123 \
    python scripts/seed_super_admin.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models.user import User
from app.utils.helpers import hash_password, generate_employee_id, log_audit
from datetime import date


def seed_super_admin():
    app = create_app()

    with app.app_context():
        # Create all tables
        db.create_all()

        # Check if super admin already exists
        existing = User.query.filter_by(role="super_admin").first()
        if existing:
            print(f"[!] Super Admin already exists: {existing.employee_id} ({existing.email})")
            print("[!] Skipping seed. Delete existing Super Admin manually if you want to recreate.")
            return

        # Get config from env
        email = os.getenv("SUPER_ADMIN_EMAIL", "superadmin@jewelcraft.com")
        password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin@123")
        first_name = os.getenv("SUPER_ADMIN_FIRST_NAME", "Super")
        last_name = os.getenv("SUPER_ADMIN_LAST_NAME", "Admin")
        phone = os.getenv("SUPER_ADMIN_PHONE", "9999999999")

        # Validate
        if len(password) < 8:
            print("[ERROR] Password must be at least 8 characters")
            return

        # Check duplicate email
        if User.query.filter_by(email=email.lower()).first():
            print(f"[ERROR] Email {email} is already in use")
            return

        employee_id = generate_employee_id("super_admin")

        super_admin = User(
            employee_id=employee_id,
            email=email.strip().lower(),
            password_hash=hash_password(password),
            role="super_admin",
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone=phone.strip(),
            date_of_joining=date.today(),
            is_active=True,
        )

        db.session.add(super_admin)
        db.session.commit()

        print("=" * 50)
        print("  SUPER ADMIN CREATED SUCCESSFULLY")
        print("=" * 50)
        print(f"  Employee ID : {employee_id}")
        print(f"  Email       : {email}")
        print(f"  Password    : {password}")
        print(f"  Name        : {first_name} {last_name}")
        print("=" * 50)
        print("  SAVE THESE CREDENTIALS SECURELY!")
        print("  Change the password after first login.")
        print("=" * 50)


if __name__ == "__main__":
    seed_super_admin()
