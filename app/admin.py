import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for, Response, jsonify

from .auth import VERIFICATION_MODES
from .db import get_db
from .utils import admin_required, save_image, to_oid, create_notification

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _list_field(field):
    """Helper to add or delete items from categories or locations."""
    uid = g.university["_id"]
    action = request.form.get("action")
    value = request.form.get("value", "").strip()
    db = get_db()
    if action == "add" and value:
        if value.lower() in [x.lower() for x in g.university.get(field, [])]:
            flash(f"'{value}' already exists.", "warning")
        else:
            db.universities.update_one({"_id": uid}, {"$push": {field: value}})
            flash(f"'{value}' has been added.", "success")
    elif action == "delete" and value:
        db.universities.update_one({"_id": uid}, {"$pull": {field: value}})
        flash(f"'{value}' has been removed.", "info")


@bp.route("/")
@admin_required
def dashboard():
    db = get_db()
    uid = g.university["_id"]

    total_lost = db.reports.count_documents({"university_id": uid, "type": "lost"})
    total_found = db.reports.count_documents({"university_id": uid, "type": "found"})
    open_reports = db.reports.count_documents({"university_id": uid, "status": "open"})
    resolved_reports = db.reports.count_documents({"university_id": uid, "status": "resolved"})
    total_all = total_lost + total_found
    recovery_rate = int((resolved_reports / total_all * 100)) if total_all > 0 else g.university.get("recovery_rate", 85)

    stats = {
        "open": open_reports,
        "resolved": resolved_reports,
        "total": total_all,
        "recovery_rate": recovery_rate,
        "users": db.users.count_documents({"university_id": uid}),
        "pending_claims": db.claims.count_documents({"university_id": uid, "status": "pending"}),
        "total_tags": db.tags.count_documents({"university_id": uid}),
    }

    # Analytics for Chart.js
    # 1. Category breakdown
    categories = g.university.get("categories", [])
    cat_counts = []
    for c in categories:
        count = db.reports.count_documents({"university_id": uid, "category": c})
        cat_counts.append(count)

    # 2. Campus Hotspots
    locations = g.university.get("locations", [])[:6]
    loc_counts = []
    for l in locations:
        count = db.reports.count_documents({"university_id": uid, "location": l})
        loc_counts.append(count)

    pending_users = list(db.users.find({"university_id": uid, "status": "pending"}).sort("created_at", 1))
    pending_claims = list(db.claims.find({"university_id": uid, "status": "pending"}).sort("created_at", 1).limit(15))
    recent_reports = list(db.reports.find({"university_id": uid}).sort("created_at", -1).limit(10))

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        pending_users=pending_users,
        pending_claims=pending_claims,
        recent_reports=recent_reports,
        chart_categories=categories,
        chart_category_counts=cat_counts,
        chart_locations=locations,
        chart_location_counts=loc_counts
    )


@bp.route("/users/<user_id>/<action>", methods=["POST"])
@admin_required
def user_action(user_id, action):
    db = get_db()
    oid = to_oid(user_id)
    scope = {"_id": oid, "university_id": g.university["_id"]}
    user = db.users.find_one(scope)

    if action == "approve" and user:
        db.users.update_one(scope, {"$set": {"status": "active"}})
        create_notification(
            user_id=user["_id"],
            university_id=g.university["_id"],
            title="Account Approved! 🎉",
            message=f"Welcome to {g.university['name']} Lost & Found Portal. Your account is now active.",
            link=url_for("reports.list_reports"),
            ntype="approval"
        )
        flash(f"User {user['name']} has been approved.", "success")
    elif action == "reject" and user:
        db.users.delete_one({**scope, "status": "pending"})
        flash(f"User registration for {user['name']} was rejected.", "info")
    return redirect(url_for("admin.dashboard"))


@bp.route("/categories", methods=["GET", "POST"])
@admin_required
def categories():
    if request.method == "POST":
        _list_field("categories")
        return redirect(url_for("admin.categories"))
    return render_template("admin/manage_list.html", title="Categories", items=g.university.get("categories", []), endpoint="admin.categories")


@bp.route("/locations", methods=["GET", "POST"])
@admin_required
def locations():
    if request.method == "POST":
        _list_field("locations")
        return redirect(url_for("admin.locations"))
    return render_template("admin/manage_list.html", title="Campus Locations", items=g.university.get("locations", []), endpoint="admin.locations")


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        mode = f.get("verification_mode", "open")
        domain = f.get("email_domain", "").strip().lower().lstrip("@")
        security_hotline = f.get("security_hotline", "").strip()
        security_office = f.get("security_office", "").strip()
        campus_size = f.get("campus_size", "").strip()
        city = f.get("city", "").strip()
        country = f.get("country", "").strip()

        if not name or mode not in VERIFICATION_MODES:
            flash("Please provide a valid university name and verification mode.", "danger")
            return redirect(url_for("admin.settings"))
        if mode == "email_domain" and not domain:
            flash("Email domain is required for domain-based verification.", "danger")
            return redirect(url_for("admin.settings"))

        update = {
            "name": name,
            "verification_mode": mode,
            "email_domain": domain,
            "security_hotline": security_hotline,
            "security_office": security_office,
            "campus_size": campus_size,
            "city": city,
            "country": country,
        }
        logo = save_image(request.files.get("logo"))
        if logo:
            update["logo_url"] = logo

        cover = save_image(request.files.get("cover"))
        if cover:
            update["cover_url"] = cover

        get_db().universities.update_one({"_id": g.university["_id"]}, {"$set": update})
        flash("University settings updated successfully.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html", modes=VERIFICATION_MODES)


@bp.route("/export/csv")
@admin_required
def export_csv():
    """Exports all university lost & found records to CSV format for security and university records."""
    db = get_db()
    reports = list(db.reports.find({"university_id": g.university["_id"]}).sort("created_at", -1))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Report ID", "Type", "Status", "Title", "Category", "Location", "Date", "Reporter Name", "Created At"])

    for r in reports:
        writer.writerow([
            str(r.get("_id")),
            r.get("type", "").upper(),
            r.get("status", "").upper(),
            r.get("title", ""),
            r.get("category", ""),
            r.get("location", ""),
            r.get("date", ""),
            r.get("reporter_name", ""),
            r.get("created_at", ""),
        ])

    filename = f"findit_{g.university.get('slug', 'campus')}_reports.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
