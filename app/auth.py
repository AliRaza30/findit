from datetime import datetime, timezone

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .utils import save_image, slugify

bp = Blueprint("auth", __name__)

VERIFICATION_MODES = {
    "open": "Open Access (instant registration for all campus members)",
    "email_domain": "Official Email Domain (@university.edu required)",
    "admin_approval": "Campus Admin Approval Required",
}


def _now():
    return datetime.now(timezone.utc)


def _login_session(user):
    session.clear()
    session["user_id"] = str(user["_id"])


@bp.route("/register-university", methods=["GET", "POST"])
@bp.route("/register_university", methods=["GET", "POST"])
def register_university():
    """Creates a new university workspace and the initial administrative account."""
    if request.method == "POST":
        f = request.form
        name = f.get("university_name", "").strip()
        city = f.get("city", "").strip()
        country = f.get("country", "").strip()
        admin_name = f.get("admin_name", "").strip()
        admin_email = f.get("admin_email", "").strip().lower()
        password = f.get("admin_password", "")
        mode = f.get("verification_mode", "open")
        domain = f.get("email_domain", "").strip().lower().lstrip("@")
        security_hotline = f.get("security_hotline", "").strip()

        if not all([name, admin_name, admin_email, password]):
            flash("Please fill in all mandatory university and administrator details.", "danger")
            return render_template("register_university.html", modes=VERIFICATION_MODES, form=f)
        if len(password) < 8:
            flash("Administrator password must be at least 8 characters long.", "danger")
            return render_template("register_university.html", modes=VERIFICATION_MODES, form=f)
        if mode not in VERIFICATION_MODES:
            mode = "open"
        if mode == "email_domain" and not domain:
            flash("Email domain is required when domain verification mode is selected.", "danger")
            return render_template("register_university.html", modes=VERIFICATION_MODES, form=f)

        db = get_db()
        slug = slugify(name)
        base, n = slug, 2
        while db.universities.find_one({"slug": slug}):
            slug = f"{base}-{n}"
            n += 1

        logo_url = save_image(request.files.get("logo"))
        cover_url = save_image(request.files.get("cover"))

        uni = {
            "name": name,
            "slug": slug,
            "city": city or "Global Campus",
            "country": country or "International",
            "recovery_rate": 85,
            "security_hotline": security_hotline or "Campus Security Desk",
            "logo_url": logo_url or "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?w=128&auto=format&fit=crop&q=80",
            "cover_url": cover_url or "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200&auto=format&fit=crop&q=80",
            "verification_mode": mode,
            "email_domain": domain,
            "categories": list(current_app.config["DEFAULT_CATEGORIES"]),
            "locations": list(current_app.config["DEFAULT_LOCATIONS"]),
            "created_at": _now(),
        }
        uni_id = db.universities.insert_one(uni).inserted_id

        admin = {
            "university_id": uni_id,
            "name": admin_name,
            "email": admin_email,
            "password_hash": generate_password_hash(password),
            "role": "admin",
            "status": "active",
            "created_at": _now(),
        }
        admin["_id"] = db.users.insert_one(admin).inserted_id
        _login_session(admin)
        flash(f"🎉 {name} workspace activated! Welcome, Administrator {admin_name}.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("register_university.html", modes=VERIFICATION_MODES, form={})


@bp.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    universities = list(db.universities.find({}, {"name": 1, "slug": 1, "verification_mode": 1, "email_domain": 1}).sort("name", 1))

    if request.method == "POST":
        f = request.form
        uni = db.universities.find_one({"slug": f.get("university", "")})
        name = f.get("name", "").strip()
        email = f.get("email", "").strip().lower()
        password = f.get("password", "")
        role = f.get("role", "student")
        phone = f.get("phone", "").strip()

        if role not in ("student", "teacher", "staff"):
            role = "student"

        if not uni or not name or not email or not password:
            flash("Please complete all required fields and select your campus.", "danger")
            return render_template("register.html", universities=universities, form=f)
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html", universities=universities, form=f)

        mode = uni.get("verification_mode", "open")
        if mode == "email_domain" and not email.endswith("@" + uni.get("email_domain", "")):
            flash(f"A valid @{uni['email_domain']} university email address is required for this campus.", "danger")
            return render_template("register.html", universities=universities, form=f)

        # Enforce Admin Approval for ALL new member registrations
        # (Students, Teachers, Staff must always be approved by the University Admin)
        status = "pending"
        user = {
            "university_id": uni["_id"],
            "name": name,
            "email": email,
            "password_hash": generate_password_hash(password),
            "role": role,
            "status": "pending",
            "phone": phone,
            "created_at": _now(),
        }
        try:
            user["_id"] = db.users.insert_one(user).inserted_id
        except DuplicateKeyError:
            flash("An account with this email address already exists at this university.", "danger")
            return render_template("register.html", universities=universities, form=f)

        # Notify the university administrator of this pending registration request
        from .utils import create_notification
        admins = list(db.users.find({"university_id": uni["_id"], "role": "admin"}))
        for adm in admins:
            create_notification(
                user_id=adm["_id"],
                university_id=uni["_id"],
                title="New Member Registration Awaiting Approval",
                message=f"{name} ({role.capitalize()}) has registered and is awaiting your verification.",
                link=url_for("admin.dashboard"),
                ntype="user_approval"
            )

        flash(f"Registration submitted for {uni['name']}! Your account has been sent to the University Administrator for approval. You can log in once approved.", "info")
        return redirect(url_for("auth.login", university=uni.get("slug")))

    return render_template("register.html", universities=universities, form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    universities = list(db.universities.find({}, {"name": 1, "slug": 1}).sort("name", 1))

    if request.method == "POST":
        f = request.form
        uni = db.universities.find_one({"slug": f.get("university", "")})
        email = f.get("email", "").strip().lower()
        password = f.get("password", "")

        user = db.users.find_one({"university_id": uni["_id"], "email": email}) if uni else None

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials or incorrect university selected. Please try again.", "danger")
            return render_template("login.html", universities=universities, form=f)

        if user.get("status") != "active":
            flash("Your registration request is pending approval by your University Administrator. Please wait for approval before logging in.", "warning")
            return render_template("login.html", universities=universities, form=f)

        _login_session(user)
        flash(f"Welcome back, {user['name']}!", "success")
        if user.get("role") == "admin":
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("main.university_portal", slug=uni["slug"]))

    return render_template("login.html", universities=universities, form={})


@bp.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    flash("You have been logged out safely.", "info")
    return redirect(url_for("main.home"))
