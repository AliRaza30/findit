from flask import Flask, g, session, request, redirect, url_for

from config import Config
from .db import init_db, get_db
from .utils import to_oid


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app)

    from .main import bp as main_bp
    from .auth import bp as auth_bp
    from .reports import bp as reports_bp
    from .admin import bp as admin_bp
    from .tags import bp as tags_bp
    from .notifications import bp as notif_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(notif_bp)

    @app.before_request
    def load_context():
        """Loads user, university workspace, and unread notifications count for every request."""
        g.user = None
        g.university = None
        g.unread_notifs_count = 0
        g.pending_approvals_count = 0
        db = get_db()

        uid = to_oid(session.get("user_id"))
        if uid:
            user = db.users.find_one({"_id": uid})
            if user and user.get("status") == "active":
                g.user = user
                g.university = db.universities.find_one({"_id": user["university_id"]})
                g.unread_notifs_count = db.notifications.count_documents({"user_id": user["_id"], "is_read": False})
                if user.get("role") == "admin" and g.university:
                    g.pending_approvals_count = db.reports.count_documents({
                        "university_id": g.university["_id"],
                        "status": "pending_approval"
                    })
            else:
                session.clear()

        # Enforce No General Public Access
        # Only authenticated campus members (Student, Teacher, Staff, Admin) can access the system.
        public_endpoints = {
            "auth.login",
            "auth.register",
            "auth.register_university",
            "main.demo_login",
            "tags.scan_tag",
            "static",
        }

        endpoint = request.endpoint
        if endpoint and endpoint not in public_endpoints and not endpoint.startswith("static"):
            if not g.user:
                return redirect(url_for("auth.login"))

    @app.context_processor
    def inject_globals():
        db = get_db()
        return {
            "current_user": g.get("user"),
            "university": g.get("university"),
            "unread_notifs_count": g.get("unread_notifs_count", 0),
            "pending_approvals_count": g.get("pending_approvals_count", 0),
            "total_universities": db.universities.count_documents({}) if db is not None else 0,
        }

    @app.template_filter("format_date")
    def format_date_filter(val, fmt="%b %d, %Y"):
        if not val:
            return ""
        if hasattr(val, "strftime"):
            return val.strftime(fmt)
        val_str = str(val)
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(val_str.replace("Z", "+00:00"))
            return dt.strftime(fmt)
        except Exception:
            return val_str[:10] if len(val_str) >= 10 else val_str

    return app
