import random
import string
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .db import get_db
from .utils import login_required, to_oid, create_notification

bp = Blueprint("tags", __name__)


def _generate_tag_code(uni_slug="FIT"):
    prefix = uni_slug[:4].upper().replace("-", "")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"FIT-{prefix}-{suffix}"


@bp.route("/tags")
@login_required
def my_tags():
    """List of all smart tags owned by the current user."""
    db = get_db()
    tags = list(db.tags.find({"user_id": g.user["_id"]}).sort("created_at", -1))
    return render_template("my_tags.html", tags=tags)


@bp.route("/tags/new", methods=["GET", "POST"])
@login_required
def new_tag():
    """Creates a new smart tag for a personal item."""
    if request.method == "POST":
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "")
        reward_message = request.form.get("reward_message", "").strip()
        anonymous_contact = request.form.get("anonymous_contact") == "1"

        if not item_name:
            flash("Please enter an item name (e.g. My MacBook Pro or Dorm Keys).", "danger")
            return redirect(url_for("tags.new_tag"))

        db = get_db()
        tag_code = _generate_tag_code(g.university.get("slug", "FIT"))
        while db.tags.find_one({"tag_code": tag_code}):
            tag_code = _generate_tag_code(g.university.get("slug", "FIT"))

        tag_doc = {
            "tag_code": tag_code,
            "user_id": g.user["_id"],
            "owner_name": g.user["name"],
            "university_id": g.university["_id"],
            "university_name": g.university["name"],
            "item_name": item_name,
            "category": category,
            "reward_message": reward_message,
            "anonymous_contact": anonymous_contact,
            "scan_count": 0,
            "created_at": datetime.now(timezone.utc),
        }
        db.tags.insert_one(tag_doc)
        flash(f"Smart Tag {tag_code} generated successfully! You can now print your QR label.", "success")
        return redirect(url_for("tags.tag_label", tag_code=tag_code))

    return render_template("tag_new.html")


@bp.route("/tags/<tag_code>/label")
@login_required
def tag_label(tag_code):
    """View and print QR sticker label for an item."""
    db = get_db()
    tag = db.tags.find_one({"tag_code": tag_code, "user_id": g.user["_id"]})
    if not tag:
        flash("Smart Tag not found.", "danger")
        return redirect(url_for("tags.my_tags"))

    public_url = request.host_url.rstrip("/") + url_for("tags.scan_tag", tag_code=tag_code)
    return render_template("tag_label.html", tag=tag, public_url=public_url)


@bp.route("/tag/<tag_code>", methods=["GET", "POST"])
def scan_tag(tag_code):
    """
    Public landing page when a finder scans a student's QR tag sticker.
    Allows anonymous recovery message submission to the owner.
    """
    db = get_db()
    tag = db.tags.find_one({"tag_code": tag_code})
    if not tag:
        return render_template("tag_not_found.html", tag_code=tag_code), 404

    # Increment scan count
    db.tags.update_one({"_id": tag["_id"]}, {"$inc": {"scan_count": 1}})

    uni = db.universities.find_one({"_id": tag["university_id"]})

    if request.method == "POST":
        finder_name = request.form.get("finder_name", "").strip() or "A fellow campus member"
        finder_contact = request.form.get("finder_contact", "").strip()
        location_found = request.form.get("location_found", "").strip()
        message = request.form.get("message", "").strip()

        if not message:
            flash("Please include a brief message on where the item is located.", "danger")
            return render_template("tag_scanned.html", tag=tag, university=uni)

        # Notify owner
        create_notification(
            user_id=tag["user_id"],
            university_id=tag["university_id"],
            title=f"🚨 SOMEONE FOUND YOUR {tag['item_name'].upper()}!",
            message=f"{finder_name} scanned your Smart Tag at '{location_found}'. Note: {message}. Contact: {finder_contact}",
            link=url_for("tags.my_tags"),
            ntype="tag_scanned"
        )

        return render_template("tag_thank_you.html", tag=tag, university=uni, finder_name=finder_name)

    return render_template("tag_scanned.html", tag=tag, university=uni)
