from flask import Flask, g, session

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
        db = get_db()

        uid = to_oid(session.get("user_id"))
        if uid:
            user = db.users.find_one({"_id": uid})
            if user and user.get("status") == "active":
                g.user = user
                g.university = db.universities.find_one({"_id": user["university_id"]})
                g.unread_notifs_count = db.notifications.count_documents({"user_id": user["_id"], "is_read": False})
            else:
                session.clear()

        # If guest is browsing an explored university
        if not g.university and session.get("guest_uni_slug"):
            g.university = db.universities.find_one({"slug": session.get("guest_uni_slug")})

    @app.context_processor
    def inject_globals():
        db = get_db()
        return {
            "current_user": g.get("user"),
            "university": g.get("university"),
            "unread_notifs_count": g.get("unread_notifs_count", 0),
            "total_universities": db.universities.count_documents({}),
        }

    return app
