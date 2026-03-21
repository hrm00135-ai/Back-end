import os
import uuid
from datetime import datetime
from flask import Blueprint, request, current_app, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required
from app.extensions import db
from app.models.user import User
from app.models.employee_profile import EmployeeProfile, BankDetail, EmployeeDocument
from app.utils.helpers import log_audit, success_response, error_response
from app.utils.encryption import encrypt_value, decrypt_value

profiles_bp = Blueprint("profiles", __name__, url_prefix="/api/profiles")

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def can_access_user(current_user, target_user_id):
    """Check if current user can access target user's profile."""
    if current_user.role == "super_admin":
        return True
    if current_user.role == "admin":
        target = User.query.get(target_user_id)
        return target and target.role == "employee"
    return current_user.id == int(target_user_id)


# ============================================================
# GET PROFILE
# ============================================================
@profiles_bp.route("/<int:user_id>", methods=["GET"])
@jwt_required()
def get_profile(user_id):
    """Get employee's extended profile."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    user = User.query.get(user_id)
    if not user:
        return error_response("User not found", 404)

    profile = EmployeeProfile.query.filter_by(user_id=user_id).first()

    result = user.to_dict()
    result["profile"] = profile.to_dict() if profile else None

    return success_response(data=result)


# ============================================================
# CREATE/UPDATE PROFILE
# ============================================================
@profiles_bp.route("/<int:user_id>", methods=["PUT"])
@jwt_required()
def update_profile(user_id):
    """Create or update employee's extended profile."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    user = User.query.get(user_id)
    if not user:
        return error_response("User not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    # Update basic user fields if provided
    basic_fields = ["first_name", "last_name", "phone", "alt_phone", "department",
                    "designation", "location_of_work"]
    for field in basic_fields:
        if field in data:
            value = data[field].strip() if isinstance(data[field], str) else data[field]
            setattr(user, field, value or None)

    # Update photo_url if provided
    if "photo_url" in data:
        user.photo_url = data["photo_url"]

    # Profile fields
    profile = EmployeeProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = EmployeeProfile(user_id=user_id)
        db.session.add(profile)

    profile_fields = [
        "date_of_birth", "gender", "blood_group", "marital_status", "nationality",
        "address_line1", "address_line2", "city", "state", "pincode",
        "perm_address_line1", "perm_address_line2", "perm_city", "perm_state", "perm_pincode",
        "emergency_contact_name", "emergency_contact_relation", "emergency_contact_phone",
        "father_name", "spouse_name",
    ]

    for field in profile_fields:
        if field in data:
            value = data[field]
            if field == "date_of_birth" and value:
                try:
                    value = datetime.strptime(value, "%Y-%m-%d").date()
                except ValueError:
                    return error_response("Invalid date_of_birth format. Use YYYY-MM-DD", 400)
            elif isinstance(value, str):
                value = value.strip() or None
            setattr(profile, field, value)

    db.session.commit()

    log_audit(int(current_user_id), "UPDATE_PROFILE", target_user_id=user_id)

    result = user.to_dict()
    result["profile"] = profile.to_dict()

    return success_response(data=result, message="Profile updated successfully")


# ============================================================
# BANK DETAILS - GET
# ============================================================
@profiles_bp.route("/<int:user_id>/bank", methods=["GET"])
@jwt_required()
def get_bank_details(user_id):
    """Get employee's bank details (masked by default)."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    bank = BankDetail.query.filter_by(user_id=user_id).first()
    if not bank:
        return success_response(data=None, message="No bank details found")

    # Only admin/super_admin can see decrypted values
    show_full = current_user.role in ("admin", "super_admin")

    result = bank.to_dict(decrypt=show_full)

    # Decrypt the encrypted fields for admin/super_admin
    if show_full:
        result["account_number"] = decrypt_value(bank.account_number_enc) if bank.account_number_enc else None
        result["pan_number"] = decrypt_value(bank.pan_number_enc) if bank.pan_number_enc else None

    return success_response(data=result)


# ============================================================
# BANK DETAILS - CREATE/UPDATE
# ============================================================
@profiles_bp.route("/<int:user_id>/bank", methods=["PUT"])
@jwt_required()
def update_bank_details(user_id):
    """Create or update bank details. Sensitive fields are encrypted."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    # Only admin/super_admin can update bank details
    if current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can update bank details", 403)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    user = User.query.get(user_id)
    if not user:
        return error_response("User not found", 404)

    data = request.get_json()
    if not data:
        return error_response("Request body is required", 400)

    bank = BankDetail.query.filter_by(user_id=user_id).first()
    if not bank:
        bank = BankDetail(user_id=user_id)
        db.session.add(bank)

    # Non-sensitive fields
    plain_fields = ["bank_name", "branch_name", "ifsc_code", "account_holder_name",
                    "uan_number", "esi_number"]
    for field in plain_fields:
        if field in data:
            setattr(bank, field, data[field].strip() if data[field] else None)

    # Encrypted fields
    if "account_number" in data and data["account_number"]:
        bank.account_number_enc = encrypt_value(data["account_number"].strip())

    if "pan_number" in data and data["pan_number"]:
        bank.pan_number_enc = encrypt_value(data["pan_number"].strip())

    db.session.commit()

    log_audit(int(current_user_id), "UPDATE_BANK_DETAILS", target_user_id=user_id)

    return success_response(
        data=bank.to_dict(decrypt=False),
        message="Bank details updated successfully"
    )


# ============================================================
# DOCUMENTS - UPLOAD
# ============================================================
@profiles_bp.route("/<int:user_id>/documents", methods=["POST"])
@jwt_required()
def upload_document(user_id):
    """Upload a document for an employee."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    user = User.query.get(user_id)
    if not user:
        return error_response("User not found", 404)

    if "file" not in request.files:
        return error_response("No file provided", 400)

    file = request.files["file"]
    doc_type = request.form.get("doc_type", "other")
    notes = request.form.get("notes", "")

    if file.filename == "":
        return error_response("No file selected", 400)

    if not allowed_file(file.filename):
        return error_response(f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", 400)

    # Check file size
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return error_response("File too large. Max 5MB", 400)

    # Generate unique filename
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{user.employee_id}_{doc_type}_{uuid.uuid4().hex[:8]}.{ext}"

    # Save to uploads/<employee_id>/
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], user.employee_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, unique_filename)
    file.save(file_path)

    # Save record
    doc = EmployeeDocument(
        user_id=user_id,
        doc_type=doc_type,
        doc_name=file.filename,
        file_path=file_path,
        file_type=ext,
        file_size=file_size,
        uploaded_by=int(current_user_id),
        notes=notes.strip() or None,
    )
    db.session.add(doc)
    db.session.commit()

    log_audit(int(current_user_id), "UPLOAD_DOCUMENT", target_user_id=user_id,
              details={"doc_type": doc_type, "filename": file.filename})

    return success_response(data=doc.to_dict(), message="Document uploaded successfully", status_code=201)


# ============================================================
# DOCUMENTS - LIST
# ============================================================
@profiles_bp.route("/<int:user_id>/documents", methods=["GET"])
@jwt_required()
def list_documents(user_id):
    """List all documents for an employee."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    doc_type = request.args.get("doc_type")
    query = EmployeeDocument.query.filter_by(user_id=user_id)

    if doc_type:
        query = query.filter_by(doc_type=doc_type)

    docs = query.order_by(EmployeeDocument.created_at.desc()).all()

    return success_response(data=[d.to_dict() for d in docs])


# ============================================================
# DOCUMENTS - DELETE
# ============================================================
@profiles_bp.route("/<int:user_id>/documents/<int:doc_id>", methods=["DELETE"])
@jwt_required()
def delete_document(user_id, doc_id):
    """Delete a document. Admin/Super Admin only."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if current_user.role not in ("admin", "super_admin"):
        return error_response("Only Admin or Super Admin can delete documents", 403)

    doc = EmployeeDocument.query.filter_by(id=doc_id, user_id=user_id).first()
    if not doc:
        return error_response("Document not found", 404)

    # Delete physical file
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.session.delete(doc)
    db.session.commit()

    log_audit(int(current_user_id), "DELETE_DOCUMENT", target_user_id=user_id,
              details={"doc_id": doc_id, "doc_type": doc.doc_type})

    return success_response(message="Document deleted successfully")


# ============================================================
# DOCUMENTS - DOWNLOAD
# ============================================================
@profiles_bp.route("/<int:user_id>/documents/<int:doc_id>/download", methods=["GET"])
@jwt_required()
def download_document(user_id, doc_id):
    """Download a document file."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    doc = EmployeeDocument.query.filter_by(id=doc_id, user_id=user_id).first()
    if not doc:
        return error_response("Document not found", 404)

    directory = os.path.dirname(doc.file_path)
    filename = os.path.basename(doc.file_path)

    return send_from_directory(directory, filename, as_attachment=True, download_name=doc.doc_name)


# ============================================================
# PHOTO UPLOAD
# ============================================================
@profiles_bp.route("/<int:user_id>/photo", methods=["POST"])
@jwt_required()
def upload_photo(user_id):
    """Upload profile photo."""
    current_user_id = get_jwt_identity()
    current_user = User.query.get(int(current_user_id))

    if not current_user:
        return error_response("User not found", 404)

    if not can_access_user(current_user, user_id):
        return error_response("Insufficient permissions", 403)

    user = User.query.get(user_id)
    if not user:
        return error_response("User not found", 404)

    if "photo" not in request.files:
        return error_response("No photo provided", 400)

    photo = request.files["photo"]
    if photo.filename == "":
        return error_response("No file selected", 400)

    ext = photo.filename.rsplit(".", 1)[1].lower() if "." in photo.filename else ""
    if ext not in {"jpg", "jpeg", "png"}:
        return error_response("Only JPG and PNG allowed", 400)

    # Check size (2MB max for photos)
    photo.seek(0, 2)
    if photo.tell() > 2 * 1024 * 1024:
        return error_response("Photo too large. Max 2MB", 400)
    photo.seek(0)

    # Save
    photo_filename = f"{user.employee_id}_photo.{ext}"
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], user.employee_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Delete old photo if exists
    if user.photo_url and os.path.exists(user.photo_url):
        os.remove(user.photo_url)

    photo_path = os.path.join(upload_dir, photo_filename)
    photo.save(photo_path)

    user.photo_url = photo_path
    db.session.commit()

    log_audit(int(current_user_id), "UPLOAD_PHOTO", target_user_id=user_id)

    return success_response(data={"photo_url": photo_path}, message="Photo uploaded successfully")