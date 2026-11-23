from datetime import datetime, timezone
from flask import Blueprint, g, redirect, render_template, request, session, url_for, jsonify

from .db import get_db
from .utils import to_oid, login_required

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    if not g.user or not g.university:
        return redirect(url_for("auth.login"))

    # Dedicated Admin Interface
    if g.user.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))

    # Dedicated Member Workspace (Student, Teacher, Staff)
    db = get_db()
    uid = g.university["_id"]
    user_id = g.user["_id"]

    stats = {
        "my_reports": db.reports.count_documents({"university_id": uid, "reporter_id": user_id}),
        "my_pending": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "pending_approval"}),
        "my_open": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "open"}),
        "my_resolved": db.reports.count_documents({"university_id": uid, "reporter_id": user_id, "status": "resolved"}),
        "my_claims": db.claims.count_documents({"university_id": uid, "claimant_id": user_id}),
        "campus_lost": db.reports.count_documents({"university_id": uid, "type": "lost", "status": "open"}),
        "campus_found": db.reports.count_documents({"university_id": uid, "type": "found", "status": "open"}),
        "campus_resolved": db.reports.count_documents({"university_id": uid, "status": "resolved"}),
        "recovery_rate": g.university.get("recovery_rate", 88),
    }

    # All reports submitted by the logged-in member (tracked with status)
    my_reports = list(db.reports.find({"university_id": uid, "reporter_id": user_id}).sort("created_at", -1))

    # Approved live campus feed
    campus_reports = list(db.reports.find({"university_id": uid, "status": "open"}).sort("created_at", -1).limit(9))

    # Claims submitted by the member with linked report details
    my_claims = list(db.claims.find({"university_id": uid, "claimant_id": user_id}).sort("created_at", -1))
    for c in my_claims:
        c["report"] = db.reports.find_one({"_id": c["report_id"]})

    # Unread notifications
    unread_notifs = list(db.notifications.find({"user_id": user_id, "is_read": False}).sort("created_at", -1).limit(5))

    return render_template(
        "home.html",
        stats=stats,
        my_reports=my_reports,
        campus_reports=campus_reports,
        my_claims=my_claims,
        unread_notifs=unread_notifs
    )


@bp.route("/universities")
@login_required
def universities_directory():
    """
    University Finder: Directory of partner university campuses for authenticated members.
    """
    db = get_db()
    query = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()

    filter_criteria = {}
    if query:
        filter_criteria["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"city": {"$regex": query, "$options": "i"}},
            {"email_domain": {"$regex": query, "$options": "i"}}
        ]
    if country:
        filter_criteria["country"] = country

    unis = list(db.universities.find(filter_criteria).sort("name", 1))

    for u in unis:
        u["open_reports_count"] = db.reports.count_documents({"university_id": u["_id"], "status": "open"})
        u["resolved_count"] = db.reports.count_documents({"university_id": u["_id"], "status": "resolved"})

    countries = db.universities.distinct("country")
    return render_template("universities_finder.html", universities=unis, search_query=query, selected_country=country, countries=countries)


@bp.route("/explore/<slug>")
@login_required
def explore_university(slug):
    """
    Explore a specific university's campus items and activity.
    """
    db = get_db()
    uni = db.universities.find_one({"slug": slug})
    if not uni:
        flash("University not found.", "warning")
        return redirect(url_for("main.universities_directory"))
    session["guest_uni_slug"] = slug
    return redirect(url_for("reports.list_reports"))


@bp.route("/demo-login/<role>")
def demo_login(role):
    """
    One-click demo login for hackathon judges & presentations.
    Provides instant access as Admin, Student, Teacher, or Staff at Apex University.
    """
    db = get_db()
    apex = db.universities.find_one({"slug": "apex-university"})
    if not apex:
        apex = db.universities.find_one({})

    if not apex:
        return redirect(url_for("auth.register_university"))

    role = role.lower()
    email_map = {
        "admin": "admin@apex.edu",
        "student": "student@apex.edu",
        "teacher": "teacher@apex.edu",
        "faculty": "teacher@apex.edu",
        "staff": "staff@apex.edu",
        "security": "staff@apex.edu",
    }
    target_email = email_map.get(role, "admin@apex.edu")

    user = db.users.find_one({"university_id": apex["_id"], "email": target_email})
    if not user:
        if role == "student":
            user = db.users.find_one({"university_id": apex["_id"], "email": "sarah@apex.edu"})
        elif role in ("teacher", "faculty"):
            user = db.users.find_one({"university_id": apex["_id"], "email": "faculty@apex.edu"})
        elif role in ("staff", "security"):
            user = db.users.find_one({"university_id": apex["_id"], "email": "marcus.security@apex.edu"})
    if not user:
        user = db.users.find_one({"university_id": apex["_id"], "role": role})
    if not user:
        user = db.users.find_one({"university_id": apex["_id"]})

    if user:
        session.clear()
        session["user_id"] = str(user["_id"])
        if user.get("role") == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.home"))

    return redirect(url_for("auth.login"))
