# JewelCraft HRM — Node.js / Express Backend

Exact 1:1 port of the Python Flask backend.  
Same models · same routes · same business logic · same API shape.

---

## Stack

| Layer       | Python (original)         | Node.js (this)         |
|-------------|---------------------------|------------------------|
| Framework   | Flask                     | Express 4              |
| ORM         | SQLAlchemy + Flask-Migrate | Sequelize 6            |
| Auth        | Flask-JWT-Extended        | jsonwebtoken           |
| File upload | Flask (request.files)     | express-fileupload     |
| Storage     | Cloudinary                | cloudinary v2          |
| Mail        | Flask-Mail                | nodemailer             |
| Encryption  | cryptography (Fernet)     | crypto (AES + HMAC)    |
| Password    | Werkzeug                  | bcrypt                 |
| Images      | Pillow                    | sharp                  |

---

## Project Structure

```
src/
  app.js              ← Express app (middleware, routes)
  server.js           ← Entry point (DB connect + listen)
  migrate.js          ← DB sync + seed super_admin
  config/
    config.js         ← All env vars (mirrors Python config.py)
    database.js       ← Sequelize instance (MySQL or SQLite)
  models/
    index.js          ← All Sequelize models + associations
  routes/
    auth.js           ← /api/auth/*
    users.js          ← /api/users/*
    profiles.js       ← /api/profiles/*
    attendance.js     ← /api/attendance/*
    leaves.js         ← /api/leaves/*
    tasks.js          ← /api/tasks/*
    payroll.js        ← /api/payroll/*
    metals.js         ← /api/metals/*
    notifications.js  ← /api/notifications/*
    payments.js       ← /api/payments/*
    reports.js        ← /api/reports/*
  utils/
    helpers.js        ← Password hash, JWT, audit log, role middleware
    encryption.js     ← Fernet-compatible AES encrypt/decrypt
    systemLogger.js   ← Tamper-proof hash-chain system log
    storage.js        ← Cloudinary upload/delete
    mailer.js         ← nodemailer send
    imageCompress.js  ← sharp image compression
  services/
    earningsCalculator.js  ← Wage type earnings + balance
```

---

## Setup

### 1. Install dependencies
```bash
npm install
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your values
```

### 3. Run database migration (creates tables + seeds super_admin)
```bash
npm run migrate
```

### 4. Start server
```bash
# Development (auto-reload)
npm run dev

# Production
npm start
```

---

## API Endpoints

### Auth — `/api/auth`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| POST   | /login                            | Public        |
| POST   | /refresh                          | JWT           |
| POST   | /logout                           | JWT           |
| GET    | /me                               | JWT           |
| POST   | /password-reset/request           | Public        |
| POST   | /password-reset/verify-otp        | Public        |
| POST   | /password-reset/approve           | Admin+        |
| GET    | /password-reset/pending           | Admin+        |
| POST   | /unlock/:userId                   | Admin+        |
| GET    | /sessions                         | Admin+        |
| GET    | /sessions/active                  | Admin+        |
| POST   | /logout/bulk                      | Admin+        |

### Users — `/api/users`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| POST   | /                                 | Admin+        |
| GET    | /                                 | Admin+        |
| GET    | /:userId                          | JWT (own/admin)|
| PUT    | /:userId                          | JWT (own/admin)|
| POST   | /:userId/photo                    | JWT (own/admin)|
| POST   | /:userId/change-password          | JWT (own/admin)|
| POST   | /:userId/deactivate               | Admin+        |
| POST   | /:userId/activate                 | Admin+        |
| GET    | /:userId/audit-logs               | Admin+        |

### Profiles — `/api/profiles`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /:userId                          | JWT (own/admin)|
| PUT    | /:userId                          | JWT (own/admin)|
| GET    | /:userId/bank                     | JWT (own/admin)|
| PUT    | /:userId/bank                     | JWT (own/admin)|
| GET    | /:userId/documents                | JWT (own/admin)|
| POST   | /:userId/documents                | JWT (own/admin)|
| DELETE | /:userId/documents/:docId         | JWT (own/admin)|

### Attendance — `/api/attendance`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /config                           | Admin+        |
| POST   | /config                           | Admin+        |
| PUT    | /config/:configId                 | Admin+        |
| POST   | /checkin                          | JWT           |
| POST   | /checkout                         | JWT           |
| GET    | /today                            | JWT           |
| GET    | /my                               | JWT           |
| GET    | /                                 | Admin+        |
| GET    | /user/:userId                     | Admin+        |
| PUT    | /:attendanceId                    | Admin+        |
| POST   | /mark-absent                      | Admin+        |
| GET    | /summary/daily                    | Admin+        |
| GET    | /summary/monthly                  | Admin+        |
| GET    | /holidays                         | JWT           |
| POST   | /holidays                         | Admin+        |
| DELETE | /holidays/:holidayId              | Admin+        |

### Leaves — `/api/leaves`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /types                            | JWT           |
| POST   | /types                            | Admin+        |
| PUT    | /types/:typeId                    | Admin+        |
| GET    | /balances/me                      | JWT           |
| GET    | /balances/:userId                 | Admin+        |
| POST   | /balances/init                    | Admin+        |
| PUT    | /balances/:userId/:leaveTypeId    | Admin+        |
| POST   | /apply                            | JWT           |
| GET    | /my                               | JWT           |
| GET    | /                                 | Admin+        |
| POST   | /:requestId/review                | Admin+        |
| POST   | /:requestId/cancel                | JWT           |

### Tasks — `/api/tasks`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| POST   | /                                 | Admin+        |
| GET    | /                                 | JWT           |
| GET    | /stats/overview                   | Admin+        |
| GET    | /:taskId                          | JWT           |
| PUT    | /:taskId                          | JWT           |
| DELETE | /:taskId                          | Admin+        |
| POST   | /:taskId/comments                 | JWT           |
| POST   | /:taskId/attachments              | JWT           |
| DELETE | /:taskId/attachments/:attachmentId| JWT           |

### Payroll — `/api/payroll`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /salary-structures                | Admin+        |
| GET    | /salary-structures/me             | JWT           |
| POST   | /salary-structures                | Admin+        |
| GET    | /daily-wages                      | Admin+        |
| GET    | /daily-wages/me                   | JWT           |
| POST   | /daily-wages                      | Admin+        |
| PUT    | /daily-wages/:wageId              | Admin+        |
| GET    | /payslips                         | Admin+        |
| GET    | /payslips/me                      | JWT           |
| POST   | /payslips/generate                | Admin+        |
| PUT    | /payslips/:payslipId/payment      | Admin+        |

### Metals — `/api/metals`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /                                 | JWT           |
| POST   | /fetch                            | Admin+        |
| POST   | /update                           | Admin+        |
| GET    | /history                          | JWT           |

### Notifications — `/api/notifications`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /                                 | JWT           |
| GET    | /unread-count                     | JWT           |
| PUT    | /mark-all-read                    | JWT           |
| PUT    | /:notificationId/read             | JWT           |
| POST   | /                                 | Admin+        |

### Payments — `/api/payments`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /config/:userId                   | Admin+        |
| POST   | /config                           | Admin+        |
| GET    | /earnings/:userId                 | Admin+        |
| GET    | /earnings/me                      | JWT           |
| POST   | /                                 | Admin+        |
| GET    | /                                 | Admin+        |
| GET    | /me                               | JWT           |
| POST   | /:txId/reverse                    | Admin+        |

### Reports — `/api/reports`
| Method | Path                              | Access        |
|--------|-----------------------------------|---------------|
| GET    | /dashboard                        | Admin+        |
| GET    | /attendance                       | Admin+        |
| GET    | /leaves                           | Admin+        |
| GET    | /payroll                          | Admin+        |
| GET    | /tasks                            | Admin+        |
| GET    | /payments                         | Admin+        |
| GET    | /audit-logs                       | Admin+        |
| GET    | /system-logs                      | SuperAdmin    |
| GET    | /system-logs/verify               | SuperAdmin    |

---

## Notes

- **Role hierarchy**: `super_admin` > `admin` > `employee`
- **JWT tokens**: Access token (15 min) + Refresh token (7 days)
- **Single-session enforcement**: Login revokes all previous refresh tokens
- **Account lock**: 5 failed attempts → locked for 30 min
- **System log chain**: SHA-256 hash chain, tamper-detectable via `/api/reports/system-logs/verify`
- **Encryption**: Bank account numbers and PAN stored encrypted (Fernet-compatible AES)
