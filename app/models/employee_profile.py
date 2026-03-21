from datetime import datetime
from app.extensions import db


class EmployeeProfile(db.Model):
    """Extended employee profile - personal details, address, emergency contact."""
    __tablename__ = "employee_profiles"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    # Personal
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.Enum("male", "female", "other", name="gender_enum"), nullable=True)
    blood_group = db.Column(db.String(10), nullable=True)
    marital_status = db.Column(db.Enum("single", "married", "divorced", "widowed", name="marital_enum"), nullable=True)
    nationality = db.Column(db.String(50), default="Indian")

    # Address - Current
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)

    # Address - Permanent
    perm_address_line1 = db.Column(db.String(255), nullable=True)
    perm_address_line2 = db.Column(db.String(255), nullable=True)
    perm_city = db.Column(db.String(100), nullable=True)
    perm_state = db.Column(db.String(100), nullable=True)
    perm_pincode = db.Column(db.String(10), nullable=True)

    # Emergency Contact
    emergency_contact_name = db.Column(db.String(100), nullable=True)
    emergency_contact_relation = db.Column(db.String(50), nullable=True)
    emergency_contact_phone = db.Column(db.String(20), nullable=True)

    # Father/Spouse
    father_name = db.Column(db.String(100), nullable=True)
    spouse_name = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = db.relationship("User", backref=db.backref("profile", uselist=False, lazy="joined"))

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "gender": self.gender,
            "blood_group": self.blood_group,
            "marital_status": self.marital_status,
            "nationality": self.nationality,
            "address_line1": self.address_line1,
            "address_line2": self.address_line2,
            "city": self.city,
            "state": self.state,
            "pincode": self.pincode,
            "perm_address_line1": self.perm_address_line1,
            "perm_address_line2": self.perm_address_line2,
            "perm_city": self.perm_city,
            "perm_state": self.perm_state,
            "perm_pincode": self.perm_pincode,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_relation": self.emergency_contact_relation,
            "emergency_contact_phone": self.emergency_contact_phone,
            "father_name": self.father_name,
            "spouse_name": self.spouse_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BankDetail(db.Model):
    """Employee bank details - encrypted sensitive fields."""
    __tablename__ = "bank_details"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    bank_name = db.Column(db.String(100), nullable=True)
    branch_name = db.Column(db.String(100), nullable=True)
    account_number_enc = db.Column(db.Text, nullable=True)  # Fernet encrypted
    ifsc_code = db.Column(db.String(20), nullable=True)
    account_holder_name = db.Column(db.String(100), nullable=True)
    pan_number_enc = db.Column(db.Text, nullable=True)  # Fernet encrypted
    uan_number = db.Column(db.String(30), nullable=True)  # PF UAN
    esi_number = db.Column(db.String(30), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("bank_detail", uselist=False, lazy="joined"))

    def to_dict(self, decrypt=False):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "bank_name": self.bank_name,
            "branch_name": self.branch_name,
            "ifsc_code": self.ifsc_code,
            "account_holder_name": self.account_holder_name,
            "uan_number": self.uan_number,
            "esi_number": self.esi_number,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if decrypt:
            data["account_number"] = self.account_number_enc  # Will be decrypted in route
            data["pan_number"] = self.pan_number_enc
        else:
            data["account_number"] = "****" + self.account_number_enc[-4:] if self.account_number_enc else None
            data["pan_number"] = "****" + self.pan_number_enc[-4:] if self.pan_number_enc else None
        return data


class EmployeeDocument(db.Model):
    """Employee document uploads - Aadhaar, PAN, offer letter, etc."""
    __tablename__ = "employee_documents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    doc_type = db.Column(
        db.Enum("aadhaar", "pan", "passport", "driving_license", "voter_id",
                "offer_letter", "experience_letter", "relieving_letter",
                "salary_slip", "bank_statement", "photo", "other",
                name="doc_type_enum"),
        nullable=False,
    )
    doc_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50), nullable=True)  # pdf, jpg, png
    file_size = db.Column(db.Integer, nullable=True)  # bytes
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notes = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id], backref="documents")
    uploader = db.relationship("User", foreign_keys=[uploaded_by])

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "doc_type": self.doc_type,
            "doc_name": self.doc_name,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "uploaded_by": self.uploaded_by,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }