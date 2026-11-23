from datetime import datetime, timezone
from flask import Blueprint, g, redirect, render_template, request, session, url_for, jsonify

from .db import get_db
from .utils import to_oid, login_required

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    """
    Main University Dashboard:
    - Displays all active partner universities as interactive cards.
    - Allows users to add a new university workspace.
    - Clicking any university opens that university's separate portal page.
    """
    db = get_db()
    query = request.args.get("q", "").strip()

    filter_criteria = {}
    if query:
        filter_criteria["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"city": {"$regex": query, "$options": "i"}},
            {"email_domain": {"$regex": query, "$options": "i"}}
        ]

    unis = list(db.universities.find(filter_criteria).sort("name", 1))

    for u in unis:
        u["lost_reports_count"] = db.reports.count_documents({
            "university_id": u["_id"],
            "type": "lost",
            "status": "open"
        })
        u["members_count"] = db.users.count_documents({
            "university_id": u["_id"],
            "status": "active"
        })

    return render_template(
        "universities_dashboard.html",
        universities=unis,
        search_query=query,
    )


@bp.route("/universities")
def universities_directory():
    """Alias for main universities dashboard."""
    return home()


@bp.route("/university/<slug>")
def university_portal(slug):
    """
    Dedicated University Page:
    - Each university has its own separate page.
    - Each university has its own separate Admin, Teachers, Students, Staff, and records.
    - Only LOST items appear on the campus feed for regular members (Found items are for Admin only).
    """
    db = get_db()
    uni = db.universities.find_one({"slug": slug})
    if not uni:
        flash("University workspace not found.", "warning")
        return redirect(url_for("main.home"))

    uid = uni["_id"]

    # If the logged-in user belongs to this specific university
    if g.user and g.user.get("university_id") == uid:
        if g.user.get("role") == "admin":
            return redirect(url_for("admin.dashboard"))

        user_id = g.user["_id"]
        stats = {
            "my_reports": db.reports.count_documents({"university_id": uid, "reporter_id": user_id}),
            "my_pending": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "pending_approval"}),
            "my_open": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "open"}),
            "my_resolved": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "resolved"}),
            "my_claims": db.claims.count_documents({"university_id": uid, "claimant_id": user_id}),
            "campus_lost": db.reports.count_documents({"university_id": uid, "type": "lost", "status": "open"}),
            "campus_resolved": db.reports.count_documents({"university_id": uid, "status": "resolved"}),
            "recovery_rate": uni.get("recovery_rate", 88),
        }

        # Reports submitted by this user
        my_reports = list(db.reports.find({"university_id": uid, "reporter_id": user_id}).sort("created_at", -1))

        # Requirement 8: ONLY Lost Item reports appear on the feed for students and other users.
        # Found item reports are strictly restricted to the University Admin.
        campus_reports = list(db.reports.find({
            "university_id": uid,
            "type": "lost",
            "status": "open"
        }).sort("created_at", -1).limit(12))

        # Claims submitted by this user
        my_claims = list(db.claims.find({"university_id": uid, "claimant_id": user_id}).sort("created_at", -1))
        for c in my_claims:
            c["report"] = db.reports.find_one({"_id": c["report_id"]})

        unread_notifs = list(db.notifications.find({"user_id": user_id, "is_read": False}).sort("created_at", -1).limit(5))

        return render_template(
            "home.html",
            stats=stats,
            my_reports=my_reports,
            campus_reports=campus_reports,
            my_claims=my_claims,
            unread_notifs=unread_notifs,
            active_university=uni,
            is_guest=False
        )

    # Guest / Not signed in to this university
    session["guest_uni_slug"] = slug
    campus_reports = list(db.reports.find({
        "university_id": uid,
        "type": "lost",
        "status": "open"
    }).sort("created_at", -1).limit(12))

    stats = {
        "my_reports": 0,
        "my_pending": 0,
        "my_open": 0,
        "my_resolved": 0,
        "my_claims": 0,
        "campus_lost": len(campus_reports),
        "campus_resolved": db.reports.count_documents({"university_id": uid, "status": "resolved"}),
        "recovery_rate": uni.get("recovery_rate", 88),
    }

    return render_template(
        "home.html",
        stats=stats,
        my_reports=[],
        campus_reports=campus_reports,
        my_claims=[],
        unread_notifs=[],
        active_university=uni,
        is_guest=True
    )


@bp.route("/explore/<slug>")
def explore_university(slug):
    """Redirect to dedicated university portal."""
    return redirect(url_for("main.university_portal", slug=slug))
