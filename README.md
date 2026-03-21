# JewelCraft HRM System - Backend API

A comprehensive HRM and workforce management system built for jewellery workshops.

## Tech Stack
- **Backend:** Python Flask + REST API
- **Database:** MySQL
- **Auth:** JWT (access + refresh tokens) + bcrypt
- **OTP:** Email-based (Flask-Mail)

---

## Quick Setup

### 1. Prerequisites
- Python 3.10+
- MySQL 8.0+
- pip

### 2. Clone & Install
```bash
cd jewelcraft
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your MySQL credentials, JWT secret, mail config
```

### 4. Create Database
```sql
CREATE DATABASE jewelcraft_hrm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. Initialize Database & Seed Super Admin
```bash
# Initialize migrations
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Seed Super Admin (the ONLY way to create one)
python scripts/seed_super_admin.py
```

### 6. Run the Server
```bash
python run.py
# Server starts at http://localhost:5000
```

---

## API Endpoints

### Health Check
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Server health check |

### Authentication
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | None | Login (all roles) |
| POST | `/api/auth/refresh` | Refresh Token | Get new access token |
| POST | `/api/auth/logout` | Access Token | Revoke refresh token |
| GET | `/api/auth/me` | Access Token | Get current user info |
| POST | `/api/auth/password-reset/request` | None | Request OTP for password reset |
| POST | `/api/auth/password-reset/verify-otp` | None | Verify OTP |
| POST | `/api/auth/password-reset/approve` | Admin/Super Admin | Approve password reset |
| GET | `/api/auth/password-reset/pending` | Admin/Super Admin | List pending reset requests |
| POST | `/api/auth/unlock/<user_id>` | Admin/Super Admin | Unlock locked account |

### User Management
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/users/register/admin` | Super Admin | Register new Admin |
| POST | `/api/users/register/employee` | Admin/Super Admin | Register new Employee |
| GET | `/api/users/` | All (role-filtered) | List users |
| GET | `/api/users/<id>` | All (role-filtered) | Get user by ID |
| POST | `/api/users/<id>/deactivate` | Admin/Super Admin | Deactivate user |

---

## Request/Response Format

### Login
```json
// POST /api/auth/login
{
    "email": "admin@example.com",
    "password": "password123"
}

// Response
{
    "status": "success",
    "message": "Login successful",
    "data": {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "user": {
            "id": 1,
            "employee_id": "SA-001",
            "email": "superadmin@jewelcraft.com",
            "role": "super_admin",
            "first_name": "Super",
            "last_name": "Admin",
            ...
        }
    }
}
```

### Register Admin (Super Admin only)
```json
// POST /api/users/register/admin
// Header: Authorization: Bearer <access_token>
{
    "email": "admin1@jewelcraft.com",
    "password": "Admin@123",
    "first_name": "John",
    "last_name": "Doe",
    "phone": "9876543210",
    "department": "Workshop",
    "designation": "Workshop Manager",
    "date_of_joining": "2026-03-22",
    "location_of_work": "Mumbai Main Workshop"
}
```

### Register Employee (Admin only)
```json
// POST /api/users/register/employee
// Header: Authorization: Bearer <access_token>
{
    "email": "emp1@jewelcraft.com",
    "password": "Emp@1234",
    "first_name": "Raj",
    "last_name": "Kumar",
    "phone": "8765432109",
    "department": "Goldsmith",
    "designation": "Senior Artisan",
    "date_of_joining": "2026-03-22",
    "location_of_work": "Mumbai Main Workshop"
}
```

### Password Reset Flow
```
Step 1: POST /api/auth/password-reset/request   → { "email": "..." }
Step 2: POST /api/auth/password-reset/verify-otp → { "otp_request_id": 1, "otp": "123456" }
Step 3: POST /api/auth/password-reset/approve    → { "otp_request_id": 1, "new_password": "..." }
        (Step 3 done by Admin for employees, Super Admin for admins)
```

---

## Role Permissions Summary

| Action | Employee | Admin | Super Admin |
|--------|----------|-------|-------------|
| Login | Yes | Yes | Yes |
| Register Employee | No | Yes | Yes |
| Register Admin | No | No | Yes |
| View own details | Yes | Yes | Yes |
| View employees | No | Yes | Yes |
| View admins | No | No | Yes |
| Approve employee password reset | No | Yes | Yes |
| Approve admin password reset | No | No | Yes |
| Unlock employee account | No | Yes | Yes |
| Unlock admin account | No | No | Yes |
| Deactivate employee | No | Yes | Yes |
| Deactivate admin | No | No | Yes |

---

## Backend-Only Operations
These can ONLY be done via CLI scripts (not API):
- Create Super Admin: `python scripts/seed_super_admin.py`
- Reset Super Admin password: `python scripts/reset_super_admin_password.py`

---

## Project Structure
```
jewelcraft/
├── app/
│   ├── __init__.py          # App factory
│   ├── extensions.py        # Flask extensions
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model
│   │   └── auth.py          # RefreshToken, OTP, AuditLog
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py          # Auth endpoints
│   │   └── users.py         # User management endpoints
│   ├── utils/
│   │   └── helpers.py       # Passwords, OTP, decorators, audit
│   └── services/
├── scripts/
│   ├── seed_super_admin.py
│   └── reset_super_admin_password.py
├── migrations/
├── config.py
├── run.py
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```
