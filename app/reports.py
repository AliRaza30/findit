import re
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for, jsonify, session

from .db import get_db
from .utils import (
    login_required,
    save_image,
    to_oid,
    find_all_matches,
    create_notification,
    get_placeholder_image,
    get_category_icon
)

bp = Blueprint("reports", __name__)


def _now():
    return datetime.now(timezone.utc)


def _get_current_or_guest_university():
    """Returns active user's university or guest explored university."""
    if g.university:
        return g.university
    db = get_db()
    guest_slug = session.get("guest_uni_slug")
    if guest_slug:
        uni = db.universities.find_one({"slug": guest_slug})
        if uni:
            return uni
    # Default to first university in system for public browsing
    return db.universities.find_one({})


def _own_report_or_404(report_id, uni=None):
    """Finds report belonging to current or explored university; returns 404 if not found."""
    oid = to_oid(report_id)
    if not oid:
        abort(404)
    db = get_db()
    if uni is None:
        uni = _get_current_or_guest_university()
    if not uni:
        abort(404)
    report = db.reports.find_one({"_id": oid, "university_id": uni["_id"]})
    if not report:
        abort(404)
    return report


def _can_manage(report):
    if not g.user:
        return False
    return g.user.get("role") in ("admin", "staff") or report.get("reporter_id") == g.user["_id"]


@bp.route("/reports")
@bp.route("/reports/")
@login_required
def list_reports():
    db = get_db()
    uni = _get_current_or_guest_university()
    if not uni:
        flash("Please select a university to browse reports.", "info")
        return redirect(url_for("main.universities_directory"))

    args = request.args
    query = {"university_id": uni["_id"]}

    is_admin = g.user.get("role") == "admin"

    if is_admin:
        status = args.get("status", "all")
        if status in ("open", "resolved", "pending_approval", "rejected"):
            query["status"] = status
    else:
        if args.get("mine"):
            query["reporter_id"] = g.user["_id"]
            status = args.get("status", "all")
            if status in ("open", "resolved", "pending_approval", "rejected"):
                query["status"] = status
        else:
            status = args.get("status", "open")
            if status in ("open", "resolved"):
                query["status"] = status
            else:
                query["status"] = "open"

    # Requirement 8: Found Item records are restricted to University Admin only.
    # Students and other users only see Lost Item reports.
    if not is_admin and not args.get("mine"):
        query["type"] = "lost"
    elif is_admin and args.get("type") in ("lost", "found"):
        query["type"] = args["type"]
    elif not is_admin and args.get("mine") and args.get("type") in ("lost", "found"):
        query["type"] = args["type"]

    if args.get("category"):
        query["category"] = args["category"]

    if args.get("location"):
        query["location"] = args["location"]

    if args.get("mine") and not is_admin:
        query["reporter_id"] = g.user["_id"]

    q = args.get("q", "").strip()
    if q:
        pattern = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": pattern}, {"description": pattern}]

    reports = list(db.reports.find(query).sort("created_at", -1).limit(100))

    # Add fallback image and icon if none provided
    for r in reports:
        if not r.get("image_url"):
            r["fallback_image"] = get_placeholder_image(r.get("category"))
        r["category_icon"] = get_category_icon(r.get("category"))

    all_universities = list(db.universities.find({}, {"name": 1, "slug": 1}))

    return render_template(
        "reports_list.html",
        reports=reports,
        args=args,
        active_uni=uni,
        all_universities=all_universities,
        is_admin=is_admin
    )


@bp.route("/map")
@login_required
def campus_map():
    """
    Interactive Campus Map View: Displays lost & found pins across campus locations with GPS coordinates.
    """
    db = get_db()
    uni = _get_current_or_guest_university()
    if not uni:
        return redirect(url_for("main.universities_directory"))

    map_query = {"university_id": uni["_id"], "status": "open"}
    if g.user and g.user.get("role") != "admin":
        map_query["type"] = "lost"
    reports = list(db.reports.find(map_query))
    coords_map = uni.get("location_coords", {})

    map_pins = []
    for r in reports:
        loc = r.get("location")
        lat = r.get("lat")
        lng = r.get("lng")

        # Fallback to predefined university location coordinates if report lat/lng not set
        if (not lat or not lng) and loc in coords_map:
            lat = coords_map[loc].get("lat")
            lng = coords_map[loc].get("lng")

        if lat and lng:
            map_pins.append({
                "id": str(r["_id"]),
                "title": r.get("title"),
                "type": r.get("type"),
                "category": r.get("category"),
                "location": r.get("location"),
                "date": r.get("date"),
                "image_url": r.get("image_url") or get_placeholder_image(r.get("category")),
                "lat": float(lat),
                "lng": float(lng),
            })

    # Default map center
    default_center = [42.3601, -71.0942]
    if coords_map:
        first_loc = next(iter(coords_map.values()))
        default_center = [first_loc["lat"], first_loc["lng"]]

    return render_template("map_view.html", active_uni=uni, map_pins=map_pins, default_center=default_center)


@bp.route("/reports/new", methods=["GET", "POST"])
@login_required
def new_report():
    uni = g.university
    if request.method == "POST":
        f = request.form
        rtype = f.get("type")
        title = f.get("title", "").strip()
        category = f.get("category", "")
        location = f.get("location", "")
        date = f.get("date", "")
        reward = f.get("reward", "").strip()
        security_q = f.get("security_question", "").strip()

        errors = []
        if rtype not in ("lost", "found"):
            errors.append("Please specify if the item was lost or found.")
        if not title:
            errors.append("Please provide a descriptive item title.")
        if category not in uni.get("categories", []):
            errors.append("Please select a valid campus category.")
        if location not in uni.get("locations", []):
            errors.append("Please select a valid campus location.")
        if not date:
            errors.append("Please select the incident date.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("report_new.html", form=f, today=datetime.now().strftime("%Y-%m-%d"))

        # Look up location coordinates from university config
        coords = uni.get("location_coords", {}).get(location, {})
        lat = coords.get("lat")
        lng = coords.get("lng")

        # Set status based on role:
        # Campus admin submissions are published immediately;
        # Student, Teacher, Staff submissions require admin verification and approval.
        is_admin = g.user.get("role") == "admin"
        status = "open" if is_admin else "pending_approval"

        report = {
            "university_id": uni["_id"],
            "reporter_id": g.user["_id"],
            "reporter_name": g.user["name"],
            "reporter_email": g.user["email"],
            "reporter_role": g.user.get("role", "student"),
            "type": rtype,
            "title": title,
            "description": f.get("description", "").strip(),
            "category": category,
            "location": location,
            "lat": lat,
            "lng": lng,
            "date": date,
            "reward": reward,
            "security_question": security_q,
            "image_url": save_image(request.files.get("image")),
            "status": status,
            "created_at": _now(),
        }

        db = get_db()
        report["_id"] = db.reports.insert_one(report).inserted_id

        if not is_admin:
            # Notify university administrators that a new submission is awaiting approval
            admins = list(db.users.find({"university_id": uni["_id"], "role": "admin"}))
            for adm in admins:
                create_notification(
                    user_id=adm["_id"],
                    university_id=uni["_id"],
                    title=f"New {rtype.upper()} Request Awaiting Approval",
                    message=f"{g.user['name']} ({g.user.get('role', 'student').capitalize()}) submitted '{title}'. Review in Admin Command Center.",
                    link=url_for("admin.dashboard"),
                    ntype="pending_approval"
                )
            flash("Your request has been submitted! Campus administration will review and approve it before it is published.", "success")
            return redirect(url_for("main.home"))

        # Evaluate instant smart matches for approved/open reports
        matches = find_all_matches(report)
        if matches:
            top_match = matches[0]
            if top_match["match_info"]["percentage"] >= 60:
                flash(
                    f"Report posted! Our AI Smart Match engine found a {top_match['match_info']['percentage']}% possible match: '{top_match['title']}'",
                    "info"
                )
                create_notification(
                    user_id=g.user["_id"],
                    university_id=uni["_id"],
                    title="Potential Match Found!",
                    message=f"We detected a {top_match['match_info']['percentage']}% match for your '{title}'.",
                    link=url_for("reports.detail", report_id=report["_id"]),
                    ntype="match"
                )

        flash("Report published successfully to the campus portal.", "success")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    return render_template(
        "report_new.html",
        form={"type": request.args.get("type", "lost")},
        today=datetime.now().strftime("%Y-%m-%d"),
        is_admin=(g.user.get("role") == "admin")
    )


@bp.route("/reports/<report_id>")
@login_required
def detail(report_id):
    uni = _get_current_or_guest_university()
    report = _own_report_or_404(report_id, uni=uni)
    db = get_db()
    is_admin = (g.user.get("role") == "admin")
    is_reporter = (report.get("reporter_id") == g.user["_id"])
    can_manage = _can_manage(report)

    # If report is pending approval, only allow admin and the reporter to view it
    if report.get("status") == "pending_approval" and not (is_admin or is_reporter):
        flash("This report is currently pending campus admin approval.", "warning")
        return redirect(url_for("reports.list_reports"))

    # Calculate smart matches if open
    matches = find_all_matches(report) if report.get("status") == "open" else []

    claims = []
    if can_manage:
        claims = list(db.claims.find({"report_id": report["_id"], "university_id": uni["_id"]}).sort("created_at", -1))

    my_claim = None
    if g.user:
        my_claim = db.claims.find_one({"report_id": report["_id"], "claimant_id": g.user["_id"]})

    # Fallback image and category icon
    if not report.get("image_url"):
        report["fallback_image"] = get_placeholder_image(report.get("category"))
    report["category_icon"] = get_category_icon(report.get("category"))

    return render_template(
        "report_detail.html",
        report=report,
        matches=matches,
        claims=claims,
        my_claim=my_claim,
        can_manage=can_manage,
        active_uni=uni,
        is_admin=is_admin,
        is_reporter=is_reporter
    )


@bp.route("/reports/<report_id>/claim", methods=["POST"])
@login_required
def claim(report_id):
    db = get_db()
    report = _own_report_or_404(report_id)

    if report.get("reporter_id") == g.user["_id"]:
        flash("You cannot claim or report finding your own item.", "warning")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    if report.get("status") != "open":
        flash("This report has already been resolved.", "warning")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    if db.claims.find_one({"report_id": report["_id"], "claimant_id": g.user["_id"]}):
        flash("You have already submitted a request for this item.", "info")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    message = request.form.get("message", "").strip()
    found_location = request.form.get("location", "").strip()
    security_answer = request.form.get("security_answer", "").strip()

    if found_location:
        full_message = f"Current Item Location: {found_location} | Notes: {message}"
    else:
        full_message = message

    if len(full_message) < 4:
        flash("Please provide brief location/recovery details.", "danger")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    is_finder = (report["type"] == "lost")
    kind = "finder" if is_finder else "ownership"

    claim_doc = {
        "university_id": g.university["_id"],
        "report_id": report["_id"],
        "claimant_id": g.user["_id"],
        "claimant_name": g.user["name"],
        "claimant_email": g.user["email"],
        "claimant_role": g.user.get("role", "student"),
        "kind": kind,
        "location": found_location,
        "message": full_message,
        "security_answer": security_answer,
        "status": "pending",
        "created_at": _now(),
    }
    db.claims.insert_one(claim_doc)

    if is_finder:
        # Finder found someone's lost item -> Request sent to Admin for verification and handover to the loser
        admins = list(db.users.find({"university_id": g.university["_id"], "role": "admin"}))
        for adm in admins:
            create_notification(
                user_id=adm["_id"],
                university_id=g.university["_id"],
                title="📦 Found Item Turned In! Awaiting Verification",
                message=f"{g.user['name']} reported finding '{report['title']}' belonging to {report['reporter_name']}. Please verify and authorize handover to the owner.",
                link=url_for("admin.dashboard"),
                ntype="item_found_turned_in"
            )

        # Notify the person who lost it (the loser)
        create_notification(
            user_id=report.get("reporter_id"),
            university_id=g.university["_id"],
            title="Good News! Your Lost Item Was Located! 📦",
            message=f"{g.user['name']} reported finding your '{report['title']}'. Campus Administration is verifying the item and will authorize handover.",
            link=url_for("reports.detail", report_id=report["_id"]),
            ntype="item_located"
        )

        flash("Thank you! Your recovery report has been submitted to Campus Administration. Admin will verify the item and authorize handover to the owner.", "success")
    else:
        # Ownership claim on a found item
        admins = list(db.users.find({"university_id": g.university["_id"], "role": "admin"}))
        for adm in admins:
            create_notification(
                user_id=adm["_id"],
                university_id=g.university["_id"],
                title="New Ownership Claim Received",
                message=f"{g.user['name']} filed an ownership claim for '{report['title']}'. Review in Admin Command Center.",
                link=url_for("admin.dashboard"),
                ntype="claim_received"
            )

        create_notification(
            user_id=report.get("reporter_id"),
            university_id=g.university["_id"],
            title="New Claim Received!",
            message=f"{g.user['name']} submitted a claim for '{report['title']}'.",
            link=url_for("reports.detail", report_id=report["_id"]),
            ntype="claim"
        )

        flash("Claim submitted successfully! Campus Administration and the reporter have been notified for verification.", "success")

    return redirect(url_for("reports.detail", report_id=report["_id"]))


@bp.route("/claims/<claim_id>/decide", methods=["POST"])
@login_required
def decide_claim(claim_id):
    db = get_db()
    oid = to_oid(claim_id)
    claim_doc = db.claims.find_one({"_id": oid, "university_id": g.university["_id"]}) if oid else None
    if not claim_doc:
        abort(404)
    report = _own_report_or_404(claim_doc["report_id"])
    if not _can_manage(report):
        abort(403)

    decision = request.form.get("decision")
    if decision not in ("approved", "rejected"):
        abort(400)

    db.claims.update_one(
        {"_id": claim_doc["_id"]},
        {"$set": {"status": decision, "decided_by": g.user["_id"], "decided_at": _now()}}
    )

    if decision == "approved":
        # Resolve report and reject other pending claims
        db.reports.update_one(
            {"_id": report["_id"]},
            {"$set": {"status": "resolved", "resolved_at": _now(), "resolved_claimant": claim_doc["claimant_id"]}}
        )
        db.claims.update_many(
            {"report_id": report["_id"], "_id": {"$ne": claim_doc["_id"]}, "status": "pending"},
            {"$set": {"status": "rejected"}},
        )

        # Notify claimant of approval
        create_notification(
            user_id=claim_doc["claimant_id"],
            university_id=g.university["_id"],
            title="Claim Approved! 🎉",
            message=f"Your claim on '{report['title']}' was approved. Check your Digital Handover Pass.",
            link=url_for("reports.handover_pass", report_id=report["_id"]),
            ntype="claim_approved"
        )
        flash(f"Claim approved! Contact claimant at {claim_doc['claimant_email']}. A digital handover pass has been issued.", "success")
    else:
        create_notification(
            user_id=claim_doc["claimant_id"],
            university_id=g.university["_id"],
            title="Claim Update",
            message=f"Your claim on '{report['title']}' was not approved.",
            link=url_for("reports.detail", report_id=report["_id"]),
            ntype="claim_rejected"
        )
        flash("Claim was rejected.", "info")

    return redirect(url_for("reports.detail", report_id=report["_id"]))


@bp.route("/reports/<report_id>/resolve", methods=["POST"])
@login_required
def resolve(report_id):
    report = _own_report_or_404(report_id)
    if not _can_manage(report):
        abort(403)
    get_db().reports.update_one(
        {"_id": report["_id"]},
        {"$set": {"status": "resolved", "resolved_at": _now()}}
    )
    flash("Report successfully marked as resolved and safely recovered.", "success")
    return redirect(url_for("reports.detail", report_id=report["_id"]))


@bp.route("/reports/<report_id>/poster")
def missing_poster(report_id):
    """
    Generates a high-visibility, print-ready Missing Item Poster with QR code and campus details.
    """
    uni = _get_current_or_guest_university()
    report = _own_report_or_404(report_id, uni=uni)

    if not report.get("image_url"):
        report["fallback_image"] = get_placeholder_image(report.get("category"))

    item_url = request.host_url.rstrip("/") + url_for("reports.detail", report_id=report["_id"])
    return render_template("poster.html", report=report, university=uni, item_url=item_url)


@bp.route("/reports/<report_id>/handover-pass")
@login_required
def handover_pass(report_id):
    """
    Digital Handover Pass: Verification pass for campus security / lost-and-found desk.
    """
    uni = g.university
    report = _own_report_or_404(report_id)
    db = get_db()

    claim_doc = db.claims.find_one({"report_id": report["_id"], "status": "approved"})

    # Check authorization: Admin, Staff, the item owner (loser/reporter), or the approved claimant
    is_owner = (report.get("reporter_id") == g.user["_id"])
    is_claimant = bool(claim_doc and claim_doc.get("claimant_id") == g.user["_id"])
    is_admin_or_staff = g.user.get("role") in ("admin", "staff")

    if not (is_owner or is_claimant or is_admin_or_staff):
        flash("Access restricted to the verified owner, finder, or campus administration.", "danger")
        return redirect(url_for("reports.detail", report_id=report["_id"]))

    verification_code = f"PASS-{str(report['_id'])[-6:].upper()}"
    return render_template(
        "handover_pass.html",
        report=report,
        claim=claim_doc,
        university=uni,
        verification_code=verification_code
    )
