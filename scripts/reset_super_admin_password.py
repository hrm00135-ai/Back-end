"""
Super Admin Password Reset Script
===================================
Reset Super Admin password via backend ONLY.
This is the ONLY way to reset a Super Admin password.

Usage:
    python scripts/reset_super_admin_password.py

Or with custom values:
    SUPER_ADMIN_EMAIL=admin@example.com \
    NEW_PASSWORD=NewSecure@456 \
    python scripts/reset_super_admin_password.py
"""

import sys
import os
import getpass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.auth import RefreshToken
from app.utils.helpers import hash_password


def reset_super_admin_password():
    app = create_app()

    with app.app_context():
        # Get email from env or prompt
        email = os.getenv("SUPER_ADMIN_EMAIL", "").strip()
        if not email:
            email = input("Enter Super Admin email: ").strip()

        user = User.query.filter_by(email=email.lower(), role="super_admin").first()
        if not user:
            print(f"[ERROR] No Super Admin found with email: {email}")
            return

        # Get new password from env or prompt
        new_password = os.getenv("NEW_PASSWORD", "").strip()
        if not new_password:
            new_password = getpass.getpass("Enter new password (min 8 chars): ")
            confirm_password = getpass.getpass("Confirm new password: ")
            if new_password != confirm_password:
                print("[ERROR] Passwords do not match")
                return

        if len(new_password) < 8:
            print("[ERROR] Password must be at least 8 characters")
            return

        # Reset password
        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.is_locked = False
        user.locked_at = None

        # Revoke all refresh tokens
        RefreshToken.query.filter_by(user_id=user.id, is_revoked=False).update(
            {"is_revoked": True}
        )

        db.session.commit()

        print("=" * 50)
        print("  SUPER ADMIN PASSWORD RESET SUCCESSFUL")
        print("=" * 50)
        print(f"  Employee ID : {user.employee_id}")
        print(f"  Email       : {user.email}")
        print("=" * 50)
        print("  All existing sessions have been revoked.")
        print("=" * 50)


if __name__ == "__main__":
    reset_super_admin_password()
