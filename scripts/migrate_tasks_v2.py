"""
Migration: Add payment_amount to tasks + create task_attachments table.
Run once on your Railway backend:
  python scripts/migrate_tasks_v2.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db

app = create_app()

SQLS = [
    # 1. Add payment_amount to tasks (if not exists)
    """
    ALTER TABLE tasks
    ADD COLUMN payment_amount FLOAT DEFAULT 0
    """,

    # 2. Create task_attachments table (if not exists)
    """
    CREATE TABLE IF NOT EXISTS task_attachments (
        id INTEGER PRIMARY KEY AUTO_INCREMENT,
        task_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        file_url VARCHAR(500) NOT NULL,
        file_type VARCHAR(20) DEFAULT 'image',
        original_name VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users(id),
        INDEX idx_task_attachments_task_id (task_id)
    )
    """,
]

with app.app_context():
    for sql in SQLS:
        try:
            db.session.execute(db.text(sql.strip()))
            db.session.commit()
            print(f"✅ OK: {sql.strip()[:60]}...")
        except Exception as e:
            db.session.rollback()
            err = str(e)
            if "Duplicate column" in err or "already exists" in err:
                print(f"⏭️  Already exists, skipping: {sql.strip()[:60]}...")
            else:
                print(f"❌ Error: {err}")

    print("\n🎉 Migration complete!")
