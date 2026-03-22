import json
from datetime import datetime
from flask import request as flask_request
from app.extensions import db
from app.models.audit import SystemLog
from app.models.user import User


def system_log(action, user_id=None, resource=None, resource_id=None,
               before=None, after=None, details=None):
    """Create a tamper-proof system log entry with hash chain."""
    
    # Get user info
    user_email = None
    user_role = None
    employee_id_str = None
    
    if user_id:
        user = User.query.get(int(user_id))
        if user:
            user_email = user.email
            user_role = user.role
            employee_id_str = user.employee_id

    # Get request info
    ip = None
    user_agent = None
    endpoint = None
    method = None
    
    try:
        ip = flask_request.headers.get("X-Forwarded-For", flask_request.remote_addr)
        user_agent = flask_request.headers.get("User-Agent", "")[:500]
        endpoint = flask_request.path
        method = flask_request.method
    except RuntimeError:
        pass  # Outside request context (e.g., CLI scripts)

    # Get previous hash for chain
    last_log = SystemLog.query.order_by(SystemLog.id.desc()).first()
    previous_hash = last_log.entry_hash if last_log else "GENESIS"

    log = SystemLog(
        user_id=int(user_id) if user_id else None,
        user_email=user_email,
        user_role=user_role,
        employee_id=employee_id_str,
        action=action,
        resource=resource,
        resource_id=resource_id,
        before_value=json.dumps(before) if isinstance(before, dict) else before,
        after_value=json.dumps(after) if isinstance(after, dict) else after,
        details=json.dumps(details) if isinstance(details, dict) else details,
        ip_address=ip,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        previous_hash=previous_hash,
        created_at=datetime.utcnow(),
    )
    log.entry_hash = log.compute_hash()

    db.session.add(log)
    db.session.commit()
    return log


def verify_log_integrity():
    """Verify the entire log chain hasn't been tampered with."""
    logs = SystemLog.query.order_by(SystemLog.id.asc()).all()
    
    if not logs:
        return {"status": "empty", "message": "No logs found"}

    broken = []
    for i, log in enumerate(logs):
        # Verify hash
        expected_hash = log.compute_hash()
        if log.entry_hash != expected_hash:
            broken.append({"id": log.id, "issue": "hash_mismatch", "expected": expected_hash, "actual": log.entry_hash})

        # Verify chain
        if i == 0:
            if log.previous_hash != "GENESIS":
                broken.append({"id": log.id, "issue": "genesis_missing"})
        else:
            if log.previous_hash != logs[i - 1].entry_hash:
                broken.append({"id": log.id, "issue": "chain_broken", "expected_prev": logs[i - 1].entry_hash, "actual_prev": log.previous_hash})

    if broken:
        return {"status": "TAMPERED", "broken_entries": broken, "total_checked": len(logs)}
    
    return {"status": "INTACT", "total_checked": len(logs), "message": "All log entries verified"}