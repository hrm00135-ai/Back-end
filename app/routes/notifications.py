from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models.notification import Notification
from app.extensions import db
from app.utils.helpers import success_response

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def get_notifications():
    user_id = int(get_jwt_identity())

    notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(Notification.created_at.desc()).limit(50).all()

    return success_response(data=[n.to_dict() for n in notifications])


@notifications_bp.route("/mark-all-read", methods=["PUT", "POST"])
@jwt_required()
def mark_all_read():
    user_id = int(get_jwt_identity())

    Notification.query.filter_by(user_id=user_id, is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()

    return success_response(message="All notifications marked as read")


# Keep old path for backwards compat
@notifications_bp.route("/read-all", methods=["PUT", "POST"])
@jwt_required()
def mark_all_read_legacy():
    return mark_all_read()


@notifications_bp.route("/<int:notif_id>/read", methods=["PUT", "POST"])
@jwt_required()
def mark_read(notif_id):
    user_id = int(get_jwt_identity())

    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if notif:
        notif.is_read = True
        db.session.commit()

    return success_response(message="Notification marked as read")
