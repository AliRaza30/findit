from datetime import datetime, timezone
from flask import Blueprint, g, redirect, render_template, request, session, url_for, jsonify

from .db import get_db
from .utils import to_oid

bp = Blueprint("main", __name__)


@bp.route("/")
def home():
    db = get_db()
    stats = None
    recent = []
    my_active_reports = []
    high_matches = []

    if g.user and g.university:
        uid = g.university["_id"]
        stats = {
            "lost": db.reports.count_documents({"university_id": uid, "type": "lost", "status": "open"}),
            "found": db.reports.count_documents({"university_id": uid, "type": "found", "status": "open"}),
            "resolved": db.reports.count_documents({"university_id": uid, "status": "resolved"}),
            "recovery_rate": g.university.get("recovery_rate", 85),
            "my_reports": db.reports.count_documents({"university_id": uid, "reporter_id": g.user["_id"]}),
            "my_claims": db.claims.count_documents({"university_id": uid, "claimant_id": g.user["_id"]}),
        }
        recent = list(db.reports.find({"university_id": uid, "status": "open"}).sort("created_at", -1).limit(6))
        my_active_reports = list(db.reports.find({"university_id": uid, "reporter_id": g.user["_id"], "status": "open"}).sort("created_at", -1).limit(3))

        # Check for unread notifications / match alerts
        unread_notifs = list(db.notifications.find({"user_id": g.user["_id"], "is_read": False}).sort("created_at", -1).limit(3))
        return render_template("home.html", stats=stats, recent=recent, my_active_reports=my_active_reports, unread_notifs=unread_notifs)

    # Public visitor landing page
    global_stats = {
        "universities_count": db.universities.count_documents({}),
        "items_recovered": db.reports.count_documents({"status": "resolved"}),
        "active_reports": db.reports.count_documents({"status": "open"}),
        "average_recovery_rate": 88,
    }
    spotlight_unis = list(db.universities.find({}).sort("recovery_rate", -1).limit(4))
    recent_public_found = list(db.reports.find({"type": "found", "status": "open"}).sort("created_at", -1).limit(4))

    return render_template("home.html", global_stats=global_stats, spotlight_unis=spotlight_unis, recent_public_found=recent_public_found)


@bp.route("/universities")
def universities_directory():
    """
    University Finder: Global directory of all partner university campuses.
    Allows searching, filtering, and entering individual campus portals.
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

    # Add active report counts to each university
    for u in unis:
        u["open_reports_count"] = db.reports.count_documents({"university_id": u["_id"], "status": "open"})
        u["resolved_count"] = db.reports.count_documents({"university_id": u["_id"], "status": "resolved"})

    countries = db.universities.distinct("country")
    return render_template("universities_finder.html", universities=unis, search_query=query, selected_country=country, countries=countries)


@bp.route("/explore/<slug>")
def explore_university(slug):
    """Sets guest viewing context to explore a specific university without registration."""
    db = get_db()
    uni = db.universities.find_one({"slug": slug})
    if not uni:
        return redirect(url_for("main.universities_directory"))
    session["guest_uni_slug"] = slug
    return redirect(url_for("reports.list_reports"))


@bp.route("/demo-login/<role>")
def demo_login(role):
    """
    One-click demo login for hackathon judges & presentations.
    Provides instant access as Admin, Student, Security, or Faculty at Apex University.
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
        "security": "security@apex.edu",
        "staff": "security@apex.edu",
        "faculty": "faculty@apex.edu",
    }
    target_email = email_map.get(role, "admin@apex.edu")

    user = db.users.find_one({"university_id": apex["_id"], "email": target_email})
    if not user:
        if role == "student":
            user = db.users.find_one({"university_id": apex["_id"], "email": "sarah@apex.edu"})
        elif role in ("security", "staff"):
            user = db.users.find_one({"university_id": apex["_id"], "email": "marcus.security@apex.edu"})
    if not user:
        user = db.users.find_one({"university_id": apex["_id"], "role": role})
    if not user:
        user = db.users.find_one({"university_id": apex["_id"]})

    if user:
        session.clear()
        session["user_id"] = str(user["_id"])
        return redirect(url_for("main.home"))

    return redirect(url_for("auth.login"))
