from flask import Blueprint, flash, g, redirect, render_template, request, url_for, jsonify
from .db import get_db
from .utils import login_required, to_oid

bp = Blueprint("notifications", __name__)


@bp.route("/notifications")
@login_required
def list_notifications():
    db = get_db()
    notifs = list(db.notifications.find({"user_id": g.user["_id"]}).sort("created_at", -1).limit(50))
    # Mark all as read when visited
    db.notifications.update_many({"user_id": g.user["_id"], "is_read": False}, {"$set": {"is_read": True}})
    return render_template("notifications.html", notifications=notifs)


@bp.route("/api/notifications/read/<notif_id>", methods=["POST"])
@login_required
def mark_read(notif_id):
    db = get_db()
    oid = to_oid(notif_id)
    if oid:
        db.notifications.update_one({"_id": oid, "user_id": g.user["_id"]}, {"$set": {"is_read": True}})
    return jsonify({"success": True})


@bp.route("/api/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    db = get_db()
    db.notifications.update_many({"user_id": g.user["_id"], "is_read": False}, {"$set": {"is_read": True}})
    return jsonify({"success": True})
