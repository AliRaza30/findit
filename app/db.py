import os
import sys
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from pymongo import MongoClient, ASCENDING, TEXT
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure

_client = None
_db = None
_is_mock = False


def _now():
    return datetime.now(timezone.utc)


def init_db(app):
    """
    Connects to MongoDB with automatic graceful fallback to mongomock
    if MongoDB is not reachable or in restricted sandbox/offline environments.
    Seeds rich sample university data if the database is newly initialized.
    """
    global _client, _db, _is_mock

    mongo_uri = app.config.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = app.config.get("MONGO_DB_NAME", "findit")
    force_mock = os.getenv("USE_MOCK_DB", "").lower() in ("1", "true", "yes")

    if not force_mock:
        try:
            # Test connection with 1.5s timeout
            test_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=1500)
            test_client.server_info()  # Will raise exception if server is down
            _client = test_client
            _db = _client[db_name]
            _is_mock = False
            print(f"[FindIt DB] Connected successfully to MongoDB at {mongo_uri} (Database: {db_name})")
        except Exception as e:
            print(f"[FindIt DB] MongoDB connection error ({e}). Falling back to MongoMock in-memory engine.")
            import mongomock
            _client = mongomock.MongoClient()
            _db = _client[db_name]
            _is_mock = True
    else:
        import mongomock
        _client = mongomock.MongoClient()
        _db = _client[db_name]
        _is_mock = True
        print(f"[FindIt DB] USE_MOCK_DB flag active: using MongoMock in-memory engine.")

    # Create Indexes safely
    try:
        _db.universities.create_index([("slug", ASCENDING)], unique=True)
        _db.users.create_index([("university_id", ASCENDING), ("email", ASCENDING)], unique=True)
        _db.reports.create_index([("university_id", ASCENDING), ("status", ASCENDING)])
        _db.reports.create_index([("title", TEXT), ("description", TEXT)])
        _db.claims.create_index([("university_id", ASCENDING), ("report_id", ASCENDING)])
        _db.tags.create_index([("tag_code", ASCENDING)], unique=True)
        _db.notifications.create_index([("user_id", ASCENDING), ("is_read", ASCENDING)])
    except Exception as e:
        # Some mock engines have partial index support; ignore non-fatal index warnings
        pass

    # Check if DB is empty; if so, automatically seed demo data for hackathon presentation
    if _db.universities.count_documents({}) == 0:
        seed_demo_data(_db)


def get_db():
    return _db


def is_mock_db():
    return _is_mock


def seed_demo_data(db):
    """Seeds rich, realistic data for an international hackathon showcase."""
    print("[FindIt DB] Seeding initial university workspaces, users, reports, and tags...")

    now = _now()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)
    three_days_ago = now - timedelta(days=3)

    # University 1: Apex International University
    apex = {
        "name": "Apex University of Science & Technology",
        "slug": "apex-university",
        "city": "Boston, MA",
        "country": "United States",
        "established": 1968,
        "campus_size": "140 Acres",
        "total_students": "18,500+",
        "recovery_rate": 87,
        "security_hotline": "+1 (617) 555-0199",
        "security_office": "Student Center, Room 104 (Lost & Found Central Desk)",
        "logo_url": "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "open",
        "email_domain": "apex.edu",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": [
            "Central Library - 2nd Floor Quiet Zone",
            "Student Union Cafeteria",
            "Engineering Lecture Hall Block B",
            "Campus Sports Complex & Gymnasium",
            "Main Campus Gate & Bus Terminal",
            "Computer Science Innovation Lab",
            "Dormitory Quadrant A",
            "Science Park Courtyard"
        ],
        "location_coords": {
            "Central Library - 2nd Floor Quiet Zone": {"lat": 42.3601, "lng": -71.0942},
            "Student Union Cafeteria": {"lat": 42.3592, "lng": -71.0930},
            "Engineering Lecture Hall Block B": {"lat": 42.3615, "lng": -71.0955},
            "Campus Sports Complex & Gymnasium": {"lat": 42.3580, "lng": -71.0968},
            "Main Campus Gate & Bus Terminal": {"lat": 42.3570, "lng": -71.0920},
            "Computer Science Innovation Lab": {"lat": 42.3610, "lng": -71.0925},
            "Dormitory Quadrant A": {"lat": 42.3622, "lng": -71.0910},
            "Science Park Courtyard": {"lat": 42.3598, "lng": -71.0960}
        },
        "created_at": three_days_ago,
    }
    apex_id = db.universities.insert_one(apex).inserted_id

    # University 2: Stanford Global Campus
    stanford = {
        "name": "Stanford University Global Campus",
        "slug": "stanford",
        "city": "Stanford, CA",
        "country": "United States",
        "established": 1885,
        "campus_size": "8,180 Acres",
        "total_students": "17,000+",
        "recovery_rate": 92,
        "security_hotline": "+1 (650) 723-9633",
        "security_office": "Tresidder Memorial Union Lost & Found Center",
        "logo_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "email_domain",
        "email_domain": "stanford.edu",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags", "Other"],
        "locations": ["Green Library", "Tresidder Union", "Huang Engineering Center", "Arrillaga Gym", "Oval Courtyard"],
        "location_coords": {
            "Green Library": {"lat": 37.4265, "lng": -122.1668},
            "Tresidder Union": {"lat": 37.4230, "lng": -122.1702},
            "Huang Engineering Center": {"lat": 37.4278, "lng": -122.1740},
            "Arrillaga Gym": {"lat": 37.4282, "lng": -122.1610},
            "Oval Courtyard": {"lat": 37.4290, "lng": -122.1695}
        },
        "created_at": three_days_ago,
    }
    db.universities.insert_one(stanford)

    # University 3: Oxford Technology Institute
    oxford = {
        "name": "Oxford Technology & Innovation Institute",
        "slug": "oxford-tech",
        "city": "Oxford",
        "country": "United Kingdom",
        "established": 1096,
        "campus_size": "Historic Campus",
        "total_students": "24,000+",
        "recovery_rate": 89,
        "security_hotline": "+44 1865 270000",
        "security_office": "Radcliffe Square Security Post",
        "logo_url": "https://images.unsplash.com/photo-1580582932707-520aed937b7b?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1548013146-72479768bada?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "oxford.ac.uk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Clothing", "Bicycles & Parts"],
        "locations": ["Radcliffe Camera", "Bodleian Library", "University Parks", "Sheldonian Theatre"],
        "location_coords": {
            "Radcliffe Camera": {"lat": 51.7534, "lng": -1.2540},
            "Bodleian Library": {"lat": 51.7540, "lng": -1.2550},
            "University Parks": {"lat": 51.7610, "lng": -1.2560},
            "Sheldonian Theatre": {"lat": 51.7548, "lng": -1.2558}
        },
        "created_at": three_days_ago,
    }
    db.universities.insert_one(oxford)

    # Seed Users for Apex University
    hashed_pwd = generate_password_hash("password123")
    admin_user = {
        "university_id": apex_id,
        "name": "Prof. Robert Sterling",
        "email": "admin@apex.edu",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    }
    admin_id = db.users.insert_one(admin_user).inserted_id

    student_sarah = {
        "university_id": apex_id,
        "name": "Sarah Jenkins",
        "email": "sarah@apex.edu",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+1 (617) 555-8391",
        "created_at": three_days_ago,
    }
    sarah_id = db.users.insert_one(student_sarah).inserted_id

    student_alex = {
        "university_id": apex_id,
        "name": "Alex Vance",
        "email": "alex@apex.edu",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+1 (617) 555-2041",
        "created_at": two_days_ago,
    }
    alex_id = db.users.insert_one(student_alex).inserted_id

    staff_officer = {
        "university_id": apex_id,
        "name": "Officer Marcus Cole",
        "email": "marcus.security@apex.edu",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+1 (617) 555-0199",
        "created_at": three_days_ago,
    }
    marcus_id = db.users.insert_one(staff_officer).inserted_id

    # Seed Reports for Apex University
    # Report 1: Lost MacBook
    rep1 = {
        "university_id": apex_id,
        "reporter_id": sarah_id,
        "reporter_name": "Sarah Jenkins",
        "type": "lost",
        "title": "Space Grey Apple MacBook Pro 14 M2",
        "description": "Left on desk 14 by the large window overlooking courtyard around 3:15 PM. Has a GitHub Octocat holographic sticker and transparent matte case.",
        "category": "Electronics",
        "location": "Central Library - 2nd Floor Quiet Zone",
        "lat": 42.3601,
        "lng": -71.0942,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=800&auto=format&fit=crop&q=80",
        "reward": "$50 Cash Reward",
        "status": "open",
        "created_at": yesterday,
    }
    rep1_id = db.reports.insert_one(rep1).inserted_id

    # Report 2: Found MacBook (Smart Match!)
    rep2 = {
        "university_id": apex_id,
        "reporter_id": alex_id,
        "reporter_name": "Alex Vance",
        "type": "found",
        "title": "Apple MacBook Pro 14 inch in Space Grey",
        "description": "Found unattended on study desk 14 on 2nd floor library near courtyard window. Handed in safely to Central Library Front Reception Desk with charger.",
        "category": "Electronics",
        "location": "Central Library - 2nd Floor Quiet Zone",
        "lat": 42.3601,
        "lng": -71.0942,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=800&auto=format&fit=crop&q=80",
        "security_question": "What holographic sticker is located on the back lid?",
        "status": "open",
        "created_at": yesterday + timedelta(hours=2),
    }
    rep2_id = db.reports.insert_one(rep2).inserted_id

    # Report 3: Lost Wallet
    rep3 = {
        "university_id": apex_id,
        "reporter_id": sarah_id,
        "reporter_name": "Sarah Jenkins",
        "type": "lost",
        "title": "Vintage Brown Leather Fossil Bifold Wallet",
        "description": "Contains Apex University Student ID card for Sarah Jenkins, CharlieCard subway pass, and family photo. Please return if found!",
        "category": "Wallet",
        "location": "Student Union Cafeteria",
        "lat": 42.3592,
        "lng": -71.0930,
        "date": two_days_ago.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800&auto=format&fit=crop&q=80",
        "reward": "Free Coffee for a Week + Gratitude",
        "status": "open",
        "created_at": two_days_ago,
    }
    rep3_id = db.reports.insert_one(rep3).inserted_id

    # Report 4: Found Sony Headphones
    rep4 = {
        "university_id": apex_id,
        "reporter_id": marcus_id,
        "reporter_name": "Officer Marcus Cole",
        "type": "found",
        "title": "Sony WH-1000XM5 Noise Cancelling Headphones",
        "description": "Midnight black Sony over-ear headphones found in grey zippered travel pouch on locker bench. Currently secured in Campus Safety Office Room 104.",
        "category": "Electronics",
        "location": "Campus Sports Complex & Gymnasium",
        "lat": 42.3580,
        "lng": -71.0968,
        "date": now.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80",
        "security_question": "What color is the audio cable inside the travel pouch?",
        "status": "open",
        "created_at": now,
    }
    rep4_id = db.reports.insert_one(rep4).inserted_id

    # Report 5: Resolved Keys
    rep5 = {
        "university_id": apex_id,
        "reporter_id": alex_id,
        "reporter_name": "Alex Vance",
        "type": "found",
        "title": "Set of Dorm Keys with Blue NASA Lanyard",
        "description": "Found on front row desk in Lecture Hall B. Returned to rightful owner via security desk.",
        "category": "Keys",
        "location": "Engineering Lecture Hall Block B",
        "lat": 42.3615,
        "lng": -71.0955,
        "date": three_days_ago.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1582139329536-e7284fece509?w=800&auto=format&fit=crop&q=80",
        "status": "resolved",
        "resolved_at": yesterday,
        "created_at": three_days_ago,
    }
    db.reports.insert_one(rep5)

    # Seed Smart Tags for Sarah
    db.tags.insert_one({
        "tag_code": "FIT-APEX-8821",
        "user_id": sarah_id,
        "university_id": apex_id,
        "item_name": "Sarah's MacBook Pro M2",
        "category": "Electronics",
        "reward_message": "If found, please contact me through FindIt! $50 reward offered.",
        "anonymous_contact": True,
        "scan_count": 3,
        "created_at": three_days_ago,
    })

    db.tags.insert_one({
        "tag_code": "FIT-APEX-4190",
        "user_id": sarah_id,
        "university_id": apex_id,
        "item_name": "Gym Duffel Bag & Keys",
        "category": "Bags & Backpacks",
        "reward_message": "Student gym bag containing essential notes and keys.",
        "anonymous_contact": True,
        "scan_count": 0,
        "created_at": two_days_ago,
    })

    # Seed Sample Notification
    db.notifications.insert_one({
        "user_id": sarah_id,
        "university_id": apex_id,
        "title": "High Confidence Match Detected!",
        "message": "A found report 'Apple MacBook Pro 14 inch in Space Grey' in Central Library matches your lost report with a 96% confidence score.",
        "link": f"/reports/{rep1_id}",
        "type": "match",
        "is_read": False,
        "created_at": yesterday + timedelta(hours=2),
    })

    print("[FindIt DB] Seed data generated successfully.")

