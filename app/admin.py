import csv
import io
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for, Response, jsonify

from .auth import VERIFICATION_MODES
from .db import get_db
from .utils import admin_required, save_image, to_oid, create_notification

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _now():
    return datetime.now(timezone.utc)


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
@admin_required # access control security rule
def dashboard():
    db = get_db()
    uid = g.university["_id"]

    total_lost = db.reports.count_documents({"university_id": uid, "type": "lost"})
    total_found = db.reports.count_documents({"university_id": uid, "type": "found"})
    pending_reports_count = db.reports.count_documents({"university_id": uid, "status": "pending_approval"})
    open_reports = db.reports.count_documents({"university_id": uid, "status": "open"})
    resolved_reports = db.reports.count_documents({"university_id": uid, "status": "resolved"})
    total_all = total_lost + total_found
    recovery_rate = int((resolved_reports / total_all * 100)) if total_all > 0 else g.university.get("recovery_rate", 85)

    stats = {
        "pending_reports": pending_reports_count,
        "pending_claims": db.claims.count_documents({"university_id": uid, "status": "pending"}),
        "open": open_reports,
        "resolved": resolved_reports,
        "total": total_all,
        "recovery_rate": recovery_rate,
        "users": db.users.count_documents({"university_id": uid}),
        "total_tags": db.tags.count_documents({"university_id": uid}),
    }

    # 1. Main Priority Queue: Items Awaiting Admin Approval
    pending_reports = list(db.reports.find({"university_id": uid, "status": "pending_approval"}).sort("created_at", 1))

    # 2. Handover Desk: Claims Awaiting Admin Decision ("give items")
    pending_claims = list(db.claims.find({"university_id": uid, "status": "pending"}).sort("created_at", 1).limit(20))
    for c in pending_claims:
        c["report"] = db.reports.find_one({"_id": c["report_id"]})

    # 3. Active / Recent Reports
    recent_reports = list(db.reports.find({"university_id": uid}).sort("created_at", -1).limit(15))

    # 4. Member Approvals
    pending_users = list(db.users.find({"university_id": uid, "status": "pending"}).sort("created_at", 1))

    # Analytics for Chart.js
    categories = g.university.get("categories", [])
    cat_counts = [db.reports.count_documents({"university_id": uid, "category": c}) for c in categories]

    locations = g.university.get("locations", [])[:6]
    loc_counts = [db.reports.count_documents({"university_id": uid, "location": l}) for l in locations]

    return render_template(
        "admin/dashboard.html",
        stats=stats,
        pending_reports=pending_reports,
        pending_claims=pending_claims,
        recent_reports=recent_reports,
        pending_users=pending_users,
        chart_categories=categories,
        chart_category_counts=cat_counts,
        chart_locations=locations,
        chart_location_counts=loc_counts
    )


@bp.route("/reports/<report_id>/approve", methods=["POST"])
@admin_required
def approve_report(report_id):
    """Admin approves a student/teacher/staff lost or found submission and makes it live."""
    db = get_db()
    oid = to_oid(report_id)
    scope = {"_id": oid, "university_id": g.university["_id"]}
    report = db.reports.find_one(scope)

    if not report:
        flash("Report not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    db.reports.update_one(scope, {
        "$set": {
            "status": "open",
            "approved_by": g.user["_id"],
            "approved_at": _now()
        }
    })

    create_notification(
        user_id=report["reporter_id"],
        university_id=g.university["_id"],
        title="Report Approved & Published! 🟢",
        message=f"Your '{report['title']}' request was approved by campus administration and is now live on the campus board.",
        link=url_for("reports.detail", report_id=report["_id"]),
        ntype="report_approved"
    )

    flash(f"Report '{report['title']}' has been approved and published to the campus portal.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.route("/reports/<report_id>/reject", methods=["POST"])
@admin_required
def reject_report(report_id):
    """Admin rejects an invalid, duplicate, or inappropriate report."""
    db = get_db()
    oid = to_oid(report_id)
    scope = {"_id": oid, "university_id": g.university["_id"]}
    report = db.reports.find_one(scope)

    if not report:
        flash("Report not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    db.reports.update_one(scope, {
        "$set": {
            "status": "rejected",
            "rejected_by": g.user["_id"],
            "rejected_at": _now()
        }
    })

    create_notification(
        user_id=report["reporter_id"],
        university_id=g.university["_id"],
        title="Report Submission Update",
        message=f"Your '{report['title']}' request was reviewed and not approved by campus administration.",
        link=url_for("reports.detail", report_id=report["_id"]),
        ntype="report_rejected"
    )

    flash(f"Report '{report['title']}' has been rejected.", "info")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.route("/reports/<report_id>/give-item", methods=["POST"])
@admin_required
def give_item(report_id, target_claim_id=None):
    """
    Admin authorizes handover of the item to claimant/owner,
    marking the report as Safely Handed Over / Resolved and generating verification code.
    """
    db = get_db()
    oid = to_oid(report_id)
    scope = {"_id": oid, "university_id": g.university["_id"]}
    report = db.reports.find_one(scope)

    if not report:
        flash("Report not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    claim_id_str = target_claim_id or request.form.get("claim_id")
    recipient_notes = request.form.get("recipient_notes", "").strip()
    claim_doc = None

    if claim_id_str:
        claim_oid = to_oid(claim_id_str)
        claim_doc = db.claims.find_one({"_id": claim_oid, "report_id": report["_id"]})

    # Mark report as resolved
    update_data = {
        "status": "resolved",
        "resolved_at": _now(),
        "resolved_by": g.user["_id"],
        "handover_notes": recipient_notes or "Handed over by Campus Administration",
    }
    if claim_doc:
        update_data["resolved_claimant"] = claim_doc["claimant_id"]

    db.reports.update_one(scope, {"$set": update_data})

    if claim_doc:
        db.claims.update_one({"_id": claim_doc["_id"]}, {"$set": {"status": "approved", "decided_at": _now(), "decided_by": g.user["_id"]}})
        db.claims.update_many({"report_id": report["_id"], "_id": {"$ne": claim_doc["_id"]}, "status": "pending"}, {"$set": {"status": "rejected"}})

        if report.get("type") == "lost":
            # Item was lost by reporter; claimant is the finder who located it
            owner_id = report.get("reporter_id")
            owner_name = report.get("reporter_name", "Owner")
            finder_id = claim_doc.get("claimant_id")
            finder_name = claim_doc.get("claimant_name", "Finder")

            # 1. Notify the owner (loser) that item has been verified and Handover Pass is issued!
            if owner_id:
                create_notification(
                    user_id=owner_id,
                    university_id=g.university["_id"],
                    title="🎉 Your Lost Item is Ready for Handover!",
                    message=f"Campus Administration verified '{report['title']}' found by {finder_name}. Open your Digital Handover Pass to collect it from the safety desk.",
                    link=url_for("reports.handover_pass", report_id=report["_id"]),
                    ntype="item_handed_over"
                )

            # 2. Notify the finder thanking them for turning in the item
            if finder_id:
                create_notification(
                    user_id=finder_id,
                    university_id=g.university["_id"],
                    title="Item Verified & Handed Over! 👏",
                    message=f"Thank you, {finder_name}! The '{report['title']}' you found has been verified by Administration and authorized for handover to {owner_name}.",
                    link=url_for("reports.detail", report_id=report["_id"]),
                    ntype="finder_verified"
                )

            flash(f"Item '{report['title']}' verified! Handover authorized to owner ({owner_name}). Digital Handover Pass issued.", "success")
        else:
            # Report was a found item; claimant is the owner
            create_notification(
                user_id=claim_doc["claimant_id"],
                university_id=g.university["_id"],
                title="Item Handed Over! 🎉",
                message=f"Your claim on '{report['title']}' was approved by campus administration. Item has been officially handed over.",
                link=url_for("reports.handover_pass", report_id=report["_id"]),
                ntype="item_handed_over"
            )
            if report.get("reporter_id"):
                create_notification(
                    user_id=report["reporter_id"],
                    university_id=g.university["_id"],
                    title="Item Safely Handed Over! 🎉",
                    message=f"Your found report '{report['title']}' has been returned to its verified owner.",
                    link=url_for("reports.detail", report_id=report["_id"]),
                    ntype="report_resolved"
                )
            flash(f"Item '{report['title']}' has been officially handed over to claimant and case marked resolved!", "success")
    else:
        # Direct resolution without specific claim
        if report.get("reporter_id"):
            create_notification(
                user_id=report["reporter_id"],
                university_id=g.university["_id"],
                title="Item Handed Over & Case Resolved! 🎉",
                message=f"Your report '{report['title']}' has been marked as safely recovered by Campus Administration.",
                link=url_for("reports.detail", report_id=report["_id"]),
                ntype="report_resolved"
            )
        flash(f"Item '{report['title']}' marked as safely recovered and resolved.", "success")
    return redirect(request.referrer or url_for("admin.dashboard"))


@bp.route("/claims/<claim_id>/give", methods=["POST"])
@admin_required
def give_claim_item(claim_id):
    """1-Click handover decision directly from Admin Claims queue."""
    db = get_db()
    c_oid = to_oid(claim_id)
    claim_doc = db.claims.find_one({"_id": c_oid, "university_id": g.university["_id"]})
    if not claim_doc:
        flash("Claim not found.", "danger")
        return redirect(url_for("admin.dashboard"))

    return give_item(str(claim_doc["report_id"]), target_claim_id=str(c_oid))


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
