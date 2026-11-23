import os
import re
import uuid
from datetime import datetime, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import current_app, flash, g, redirect, url_for
from werkzeug.utils import secure_filename

STOP_WORDS = {
    "the", "a", "an", "is", "in", "on", "at", "of", "and", "or", "my", "with",
    "to", "for", "from", "by", "it", "this", "that", "was", "were", "found", "lost",
    "ka", "ki", "ke", "hai", "ek", "mera", "meri", "kahan", "bhi"
}

CATEGORY_ICONS = {
    "Electronics": "fa-laptop",
    "Wallet": "fa-wallet",
    "Documents & IDs": "fa-id-card",
    "Documents": "fa-id-card",
    "Keys": "fa-key",
    "Bags & Backpacks": "fa-backpack",
    "Bags": "fa-backpack",
    "Clothing & Gear": "fa-tshirt",
    "Clothing": "fa-tshirt",
    "Watches & Jewelry": "fa-ring",
    "Books & Study Material": "fa-book",
    "Bicycles & Parts": "fa-bicycle",
    "Other": "fa-box",
}

CATEGORY_IMAGES = {
    "Electronics": "https://images.unsplash.com/photo-1468495244123-6c6c332eeece?w=600&auto=format&fit=crop&q=80",
    "Wallet": "https://images.unsplash.com/photo-1627123424574-724758594e93?w=600&auto=format&fit=crop&q=80",
    "Documents & IDs": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=600&auto=format&fit=crop&q=80",
    "Documents": "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=600&auto=format&fit=crop&q=80",
    "Keys": "https://images.unsplash.com/photo-1582139329536-e7284fece509?w=600&auto=format&fit=crop&q=80",
    "Bags & Backpacks": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&auto=format&fit=crop&q=80",
    "Bags": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&auto=format&fit=crop&q=80",
    "Clothing & Gear": "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop&q=80",
    "Clothing": "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=600&auto=format&fit=crop&q=80",
    "Watches & Jewelry": "https://images.unsplash.com/photo-1524805444758-089113d48a6d?w=600&auto=format&fit=crop&q=80",
    "Books & Study Material": "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?w=600&auto=format&fit=crop&q=80",
    "Bicycles & Parts": "https://images.unsplash.com/photo-1485965120184-e220f721d03e?w=600&auto=format&fit=crop&q=80",
    "Other": "https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?w=600&auto=format&fit=crop&q=80",
}


def to_oid(value):
    """Safely converts string to ObjectId; returns None on invalid inputs."""
    if not value:
        return None
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "university"


def allowed_image(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


def save_image(file_storage):
    """Saves image to Cloudinary (if configured), local uploads folder, or base64 fallback on read-only serverless."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        return None

    if current_app.config.get("CLOUDINARY_URL"):
        try:
            import cloudinary.uploader
            result = cloudinary.uploader.upload(file_storage, folder="findit")
            return result["secure_url"]
        except Exception:
            pass  # fallback to local upload

    folder = current_app.config.get("UPLOAD_FOLDER")
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"

    try:
        os.makedirs(folder, exist_ok=True)
        file_storage.save(os.path.join(folder, name))
        return url_for("static", filename=f"uploads/{name}")
    except OSError:
        # Fallback for serverless read-only filesystems (e.g. Vercel)
        import base64
        try:
            file_storage.seek(0)
            data = file_storage.read()
            mime = "image/" + (ext if ext in ("png", "jpg", "jpeg", "webp", "gif") else "jpeg")
            encoded = base64.b64encode(data).decode("utf-8")
            return f"data:{mime};base64,{encoded}"
        except Exception:
            return None


def get_category_icon(category):
    return CATEGORY_ICONS.get(category, "fa-box")


def get_placeholder_image(category):
    return CATEGORY_IMAGES.get(category, CATEGORY_IMAGES["Other"])


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to access this feature.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "warning")
            return redirect(url_for("auth.login"))
        if g.user.get("role") != "admin":
            flash("This page is restricted to university administrators only.", "danger")
            return redirect(url_for("main.home"))
        return view(*args, **kwargs)

    return wrapped


def create_notification(user_id, university_id, title, message, link="#", ntype="system"):
    """Creates an in-app notification for a user."""
    from .db import get_db
    db = get_db()
    if not user_id or not university_id:
        return None
    doc = {
        "user_id": user_id,
        "university_id": university_id,
        "title": title,
        "message": message,
        "link": link,
        "type": ntype,
        "is_read": False,
        "created_at": datetime.now(timezone.utc),
    }
    return db.notifications.insert_one(doc).inserted_id


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP_WORDS and len(w) > 2}


def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def calculate_smart_match(rep1, rep2):
    """
    Evaluates match probability (0 to 100%) between opposite reports.
    Returns: dict(percentage, score, reasons, matched_tokens)
    """
    score = 0
    max_score = 100
    reasons = []

    # 1. Category Match (Base weight: 25%)
    if rep1.get("category") == rep2.get("category"):
        score += 25
        reasons.append(f"Category: {rep1.get('category')}")
    else:
        # Without matching category, match probability is severely reduced
        return {"percentage": 0, "score": 0, "reasons": []}

    # 2. Textual overlap in title and description (Weight: up to 40%)
    tokens1 = _tokens(rep1.get("title", "") + " " + rep1.get("description", ""))
    tokens2 = _tokens(rep2.get("title", "") + " " + rep2.get("description", ""))
    common = tokens1 & tokens2
    if common:
        overlap_ratio = len(common) / max(len(tokens1 | tokens2), 1)
        token_points = min(40, int(len(common) * 10 + overlap_ratio * 20))
        score += token_points
        keywords_str = ", ".join(list(common)[:4])
        reasons.append(f"Matching keywords: {keywords_str}")

    # 3. Location Proximity (Weight: up to 20%)
    loc1 = rep1.get("location", "").strip().lower()
    loc2 = rep2.get("location", "").strip().lower()
    if loc1 and loc2 and loc1 == loc2:
        score += 20
        reasons.append(f"Identical location: {rep1.get('location')}")
    elif loc1 and loc2 and (loc1 in loc2 or loc2 in loc1):
        score += 12
        reasons.append("Nearby campus area")

    # 4. Temporal Proximity (Weight: up to 15%)
    d1 = _parse_date(rep1.get("date"))
    d2 = _parse_date(rep2.get("date"))
    if d1 and d2:
        diff_days = abs((d1 - d2).days)
        if diff_days == 0:
            score += 15
            reasons.append("Reported on the exact same date")
        elif diff_days <= 2:
            score += 10
            reasons.append(f"Reported within {diff_days} day(s)")
        elif diff_days <= 5:
            score += 5
            reasons.append("Reported within the same week")

    percentage = min(99, max(0, score))
    return {
        "percentage": percentage,
        "score": score,
        "reasons": reasons,
        "matched_tokens": list(common)
    }


def find_all_matches(report, limit=6):
    """
    Finds top matching opposite reports within the university with smart match calculation.
    """
    from .db import get_db
    db = get_db()
    opposite = "found" if report["type"] == "lost" else "lost"

    candidates = db.reports.find({
        "university_id": report["university_id"],
        "type": opposite,
        "status": "open",
        "category": report["category"],
        "_id": {"$ne": report["_id"]}
    })

    scored = []
    for cand in candidates:
        match_info = calculate_smart_match(report, cand)
        if match_info["percentage"] >= 35:
            cand["match_info"] = match_info
            scored.append((match_info["percentage"], cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]
