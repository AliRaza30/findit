import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING, MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

_client = None
_db = None
_is_mock = False


def _now():
    return datetime.now(timezone.utc)


def init_db(app):
    """Initializes MongoDB connection using Config URI with seamless fallback to MongoMock."""
    global _client, _db, _is_mock

    mongo_uri = app.config.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = app.config.get("MONGO_DB_NAME", "findit")

    try:
        # Use short serverSelectionTimeoutMS so we fail fast to mock in isolated local testing
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        _client = client
        _db = client[db_name]
        _is_mock = False
        print(f"[FindIt DB] Connected successfully to MongoDB at {mongo_uri} (Database: {db_name})")
    except Exception as e:
        print(f"[FindIt DB] MongoDB connection error ({e}). Falling back to MongoMock in-memory engine.")
        try:
            import mongomock
            _client = mongomock.MongoClient()
            _db = _client[db_name]
            _is_mock = True
        except ImportError:
            raise RuntimeError("Neither live MongoDB nor mongomock is available. Please install mongomock: pip install mongomock")

    # Set up indexes safely
    try:
        _db.universities.create_index("slug", unique=True)
        _db.users.create_index([("university_id", ASCENDING), ("email", ASCENDING)], unique=True)
        _db.reports.create_index([("university_id", ASCENDING), ("status", ASCENDING)])
        _db.reports.create_index([("university_id", ASCENDING), ("type", ASCENDING)])
        _db.claims.create_index([("report_id", ASCENDING), ("claimant_id", ASCENDING)])
        _db.tags.create_index("tag_code", unique=True)
        _db.notifications.create_index([("user_id", ASCENDING), ("is_read", ASCENDING)])
    except Exception as idx_err:
        pass

    # Check if DB is empty; if so, automatically seed Pakistani universities data
    try:
        if _db.universities.count_documents({}) == 0:
            seed_demo_data(_db)
    except Exception as seed_err:
        print(f"[FindIt DB] Note during initial check: {seed_err}")

    return _db


def get_db():
    return _db


def is_mock_db():
    return _is_mock


def seed_demo_data(db):
    """Seeds realistic Pakistani universities, users, and lost items using existing project images."""
    print("[FindIt DB] Seeding Pakistani universities, users, and campus lost records...")

    now = _now()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)
    three_days_ago = now - timedelta(days=3)

    hashed_pwd = generate_password_hash("password123")

    # ================= 1. NUST ISLAMABAD =================
    nust = {
        "name": "National University of Sciences & Technology (NUST)",
        "slug": "nust-islamabad",
        "city": "Islamabad",
        "country": "Pakistan",
        "established": 1991,
        "campus_size": "Sector H-12, 700 Acres",
        "total_students": "15,000+",
        "recovery_rate": 91,
        "security_hotline": "+92 (51) 9085-1199",
        "security_office": "Sector H-12 Main Security Directorate & Lost Property Office",
        "logo_url": "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "nust.edu.pk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": ["Central Library - 2nd Floor Quiet Zone", "Concordia 1 Cafeteria", "SEECS Lecture Hall Block B", "Sports Complex & Gymnasium", "H-12 Main Gate & Bus Terminal", "RIMMS Research Lab"],
        "location_coords": {
            "Central Library - 2nd Floor Quiet Zone": {"lat": 33.6425, "lng": 72.9904},
            "Concordia 1 Cafeteria": {"lat": 33.6432, "lng": 72.9918},
            "SEECS Lecture Hall Block B": {"lat": 33.6441, "lng": 72.9930},
            "Sports Complex & Gymnasium": {"lat": 33.6410, "lng": 72.9880},
            "H-12 Main Gate & Bus Terminal": {"lat": 33.6400, "lng": 72.9950},
            "RIMMS Research Lab": {"lat": 33.6450, "lng": 72.9910}
        },
        "created_at": three_days_ago,
    }
    nust_id = db.universities.insert_one(nust).inserted_id

    # NUST Users
    nust_admin_id = db.users.insert_one({
        "university_id": nust_id,
        "name": "Dr. Muhammad Tariq (Registrar & Admin)",
        "email": "admin@nust.edu.pk",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    }).inserted_id

    nust_student_id = db.users.insert_one({
        "university_id": nust_id,
        "name": "Hamza Ahmed",
        "email": "hamza.ahmed@nust.edu.pk",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+92 300 5551234",
        "created_at": three_days_ago,
    }).inserted_id

    nust_teacher_id = db.users.insert_one({
        "university_id": nust_id,
        "name": "Prof. Ayesha Malik",
        "email": "ayesha.malik@nust.edu.pk",
        "password_hash": hashed_pwd,
        "role": "teacher",
        "status": "active",
        "phone": "+92 301 5554321",
        "created_at": three_days_ago,
    }).inserted_id

    db.users.insert_one({
        "university_id": nust_id,
        "name": "Subedar (R) Muhammad Rasheed",
        "email": "security@nust.edu.pk",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+92 302 5559876",
        "created_at": three_days_ago,
    })

    # NUST Lost Items (Existing pictures only, no reward)
    nust_rep1_id = db.reports.insert_one({
        "university_id": nust_id,
        "reporter_id": nust_student_id,
        "reporter_name": "Hamza Ahmed",
        "reporter_email": "hamza.ahmed@nust.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "Space Grey Apple MacBook Pro 14 M2",
        "description": "Left on desk 14 by the window in Central Library around 3:15 PM. Has a GitHub sticker on the back lid.",
        "category": "Electronics",
        "location": "Central Library - 2nd Floor Quiet Zone",
        "lat": 33.6425,
        "lng": 72.9904,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": yesterday,
    }).inserted_id

    db.reports.insert_one({
        "university_id": nust_id,
        "reporter_id": nust_teacher_id,
        "reporter_name": "Prof. Ayesha Malik",
        "reporter_email": "ayesha.malik@nust.edu.pk",
        "reporter_role": "teacher",
        "type": "lost",
        "title": "Vintage Brown Leather Fossil Bifold Wallet",
        "description": "Contains NUST Faculty Card for Prof. Ayesha Malik, CNIC, and Metro Card. Please return if found.",
        "category": "Wallet",
        "location": "Concordia 1 Cafeteria",
        "lat": 33.6432,
        "lng": 72.9918,
        "date": two_days_ago.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": two_days_ago,
    })


    # ================= 2. FAST NUCES LAHORE =================
    fast = {
        "name": "FAST NUCES - National University of Computer & Emerging Sciences",
        "slug": "fast-nuces-lahore",
        "city": "Lahore",
        "country": "Pakistan",
        "established": 2000,
        "campus_size": "Faisal Town Campus, 12 Acres",
        "total_students": "6,500+",
        "recovery_rate": 89,
        "security_hotline": "+92 (42) 111-128-128",
        "security_office": "Block B Security Office & Lost Property Desk Room 102",
        "logo_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "nu.edu.pk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": ["CS Innovation Lab Block B", "Campus Cafeteria & Lawn", "Main Library Reading Hall", "Sports Ground Court", "Main Gate Reception"],
        "location_coords": {
            "CS Innovation Lab Block B": {"lat": 31.4815, "lng": 74.3030},
            "Campus Cafeteria & Lawn": {"lat": 31.4810, "lng": 74.3038},
            "Main Library Reading Hall": {"lat": 31.4820, "lng": 74.3025},
            "Sports Ground Court": {"lat": 31.4805, "lng": 74.3045},
            "Main Gate Reception": {"lat": 31.4825, "lng": 74.3020}
        },
        "created_at": three_days_ago,
    }
    fast_id = db.universities.insert_one(fast).inserted_id

    # FAST Users
    fast_admin_id = db.users.insert_one({
        "university_id": fast_id,
        "name": "Dr. Zeeshan Ali (Director Admin)",
        "email": "admin@nu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    }).inserted_id

    fast_student_id = db.users.insert_one({
        "university_id": fast_id,
        "name": "Fatima Zahra",
        "email": "fatima.zahra@nu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+92 321 4441122",
        "created_at": three_days_ago,
    }).inserted_id

    fast_teacher_id = db.users.insert_one({
        "university_id": fast_id,
        "name": "Dr. Farhan Siddiqui (HOD Software Engineering)",
        "email": "farhan.siddiqui@nu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "teacher",
        "status": "active",
        "phone": "+92 322 4443344",
        "created_at": three_days_ago,
    }).inserted_id

    db.users.insert_one({
        "university_id": fast_id,
        "name": "Muhammad Aslam (Security Supervisor)",
        "email": "security@nu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+92 323 4445566",
        "created_at": three_days_ago,
    })

    # FAST Lost Items
    db.reports.insert_one({
        "university_id": fast_id,
        "reporter_id": fast_student_id,
        "reporter_name": "Fatima Zahra",
        "reporter_email": "fatima.zahra@nu.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "Sony WH-1000XM5 Noise Cancelling Headphones",
        "description": "Black over-ear Sony headphones in a grey zippered pouch. Left near computer workstation #18.",
        "category": "Electronics",
        "location": "CS Innovation Lab Block B",
        "lat": 31.4815,
        "lng": 74.3030,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": yesterday,
    })

    db.reports.insert_one({
        "university_id": fast_id,
        "reporter_id": fast_teacher_id,
        "reporter_name": "Dr. Farhan Siddiqui",
        "reporter_email": "farhan.siddiqui@nu.edu.pk",
        "reporter_role": "teacher",
        "type": "lost",
        "title": "Set of Dorm Keys with Blue NASA Lanyard",
        "description": "Three silver keys attached to a blue NASA lanyard. Misplaced after lab class.",
        "category": "Keys",
        "location": "Campus Cafeteria & Lawn",
        "lat": 31.4810,
        "lng": 74.3038,
        "date": two_days_ago.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1582139329536-e7284fece509?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": two_days_ago,
    })


    # ================= 3. LUMS LAHORE =================
    lums = {
        "name": "Lahore University of Management Sciences (LUMS)",
        "slug": "lums-lahore",
        "city": "Lahore",
        "country": "Pakistan",
        "established": 1984,
        "campus_size": "DHA Phase 5, 100 Acres",
        "total_students": "5,000+",
        "recovery_rate": 93,
        "security_hotline": "+92 (42) 3560-8000",
        "security_office": "DHA Phase 5 Campus Safety Command Office Gate 1",
        "logo_url": "https://images.unsplash.com/photo-1580582932707-520aed937b7b?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1548013146-72479768bada?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "lums.edu.pk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": ["Gad & Birgit Rausing Library", "PDC Executive Dining Hall", "Suleman Dawood School of Business", "Sports Complex Aquatic Center", "Gate 1 Reception"],
        "location_coords": {
            "Gad & Birgit Rausing Library": {"lat": 31.4705, "lng": 74.4100},
            "PDC Executive Dining Hall": {"lat": 31.4712, "lng": 74.4115},
            "Suleman Dawood School of Business": {"lat": 31.4698, "lng": 74.4090},
            "Sports Complex Aquatic Center": {"lat": 31.4720, "lng": 74.4080},
            "Gate 1 Reception": {"lat": 31.4690, "lng": 74.4120}
        },
        "created_at": three_days_ago,
    }
    lums_id = db.universities.insert_one(lums).inserted_id

    # LUMS Users
    lums_admin_id = db.users.insert_one({
        "university_id": lums_id,
        "name": "Dr. Syed Babar Ali (Campus Administration)",
        "email": "admin@lums.edu.pk",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    }).inserted_id

    lums_student_id = db.users.insert_one({
        "university_id": lums_id,
        "name": "Usman Qureshi",
        "email": "usman.qureshi@lums.edu.pk",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+92 333 7778899",
        "created_at": three_days_ago,
    }).inserted_id

    db.users.insert_one({
        "university_id": lums_id,
        "name": "Dr. Bilal Khan (Associate Professor)",
        "email": "bilal.khan@lums.edu.pk",
        "password_hash": hashed_pwd,
        "role": "teacher",
        "status": "active",
        "phone": "+92 334 7771122",
        "created_at": three_days_ago,
    })

    db.users.insert_one({
        "university_id": lums_id,
        "name": "Tariq Mehmood (Campus Security)",
        "email": "security@lums.edu.pk",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+92 335 7773344",
        "created_at": three_days_ago,
    })

    # LUMS Lost Items
    db.reports.insert_one({
        "university_id": lums_id,
        "reporter_id": lums_student_id,
        "reporter_name": "Usman Qureshi",
        "reporter_email": "usman.qureshi@lums.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "TI-84 Plus CE Color Graphing Calculator",
        "description": "Left on 1st floor cubicle table in Rausing Library. Has yellow label with name on sliding cover.",
        "category": "Electronics",
        "location": "Gad & Birgit Rausing Library",
        "lat": 31.4705,
        "lng": 74.4100,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": yesterday,
    })

    db.reports.insert_one({
        "university_id": lums_id,
        "reporter_id": lums_student_id,
        "reporter_name": "Usman Qureshi",
        "reporter_email": "usman.qureshi@lums.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "Pacific Blue Hydro Flask 32oz Wide Mouth",
        "description": "Blue insulated stainless water bottle left on bleachers near gym.",
        "category": "Personal Items",
        "location": "Sports Complex Aquatic Center",
        "lat": 31.4720,
        "lng": 74.4080,
        "date": two_days_ago.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1602143407151-7111542de6e8?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": two_days_ago,
    })


    # ================= 4. GIKI TOPI =================
    giki = {
        "name": "GIK Institute of Engineering Sciences and Technology",
        "slug": "giki-topi",
        "city": "Topi, Swabi",
        "country": "Pakistan",
        "established": 1993,
        "campus_size": "KPK Foothills, 400 Acres",
        "total_students": "2,500+",
        "recovery_rate": 90,
        "security_hotline": "+92 (938) 271858",
        "security_office": "Main Faculty Gate Security Post & Lost Property Office",
        "logo_url": "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "giki.edu.pk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": ["Agha Hasan Abedi Auditorium", "Central Library", "Faculty of Mechanical Engineering", "Hostel 4 Common Room", "Main Gate"],
        "location_coords": {
            "Agha Hasan Abedi Auditorium": {"lat": 34.0700, "lng": 72.6450},
            "Central Library": {"lat": 34.0710, "lng": 72.6460},
            "Faculty of Mechanical Engineering": {"lat": 34.0690, "lng": 72.6440},
            "Hostel 4 Common Room": {"lat": 34.0720, "lng": 72.6470},
            "Main Gate": {"lat": 34.0680, "lng": 72.6430}
        },
        "created_at": three_days_ago,
    }
    giki_id = db.universities.insert_one(giki).inserted_id

    # GIKI Users
    db.users.insert_one({
        "university_id": giki_id,
        "name": "Dr. Fazal Ahmad Khalid (Rector & Admin)",
        "email": "admin@giki.edu.pk",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    })

    giki_student_id = db.users.insert_one({
        "university_id": giki_id,
        "name": "Saad Rehman",
        "email": "saad.rehman@giki.edu.pk",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+92 345 9998877",
        "created_at": three_days_ago,
    }).inserted_id

    db.users.insert_one({
        "university_id": giki_id,
        "name": "Engr. Zainab Bibi",
        "email": "zainab.bibi@giki.edu.pk",
        "password_hash": hashed_pwd,
        "role": "teacher",
        "status": "active",
        "phone": "+92 346 9991122",
        "created_at": three_days_ago,
    })

    db.users.insert_one({
        "university_id": giki_id,
        "name": "Gulzar Khan (Security Incharge)",
        "email": "security@giki.edu.pk",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+92 347 9993344",
        "created_at": three_days_ago,
    })

    # GIKI Lost Item
    db.reports.insert_one({
        "university_id": giki_id,
        "reporter_id": giki_student_id,
        "reporter_name": "Saad Rehman",
        "reporter_email": "saad.rehman@giki.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "Apple MacBook Pro 14 inch in Space Grey",
        "description": "Left on 2nd row seat in Auditorium after IEEE guest lecture.",
        "category": "Electronics",
        "location": "Agha Hasan Abedi Auditorium",
        "lat": 34.0700,
        "lng": 72.6450,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1611186871348-b1ce696e52c9?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": yesterday,
    })


    # ================= 5. UNIVERSITY OF THE PUNJAB (PU) =================
    pu = {
        "name": "University of the Punjab (PU)",
        "slug": "pu-lahore",
        "city": "Lahore",
        "country": "Pakistan",
        "established": 1882,
        "campus_size": "Quaid-e-Azam New Campus, 1,800 Acres",
        "total_students": "45,000+",
        "recovery_rate": 88,
        "security_hotline": "+92 (42) 9923-1100",
        "security_office": "New Campus Gate 2 Chief Security Directorate Office",
        "logo_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=128&auto=format&fit=crop&q=80",
        "cover_url": "https://images.unsplash.com/photo-1562774053-701939374585?w=1200&auto=format&fit=crop&q=80",
        "verification_mode": "admin_approval",
        "email_domain": "pu.edu.pk",
        "categories": ["Electronics", "Wallet", "Documents & IDs", "Keys", "Bags & Backpacks", "Clothing & Gear", "Watches & Jewelry", "Books & Study Material"],
        "locations": ["Punjab University Central Library", "Department of Information Technology", "Institute of Business Administration", "New Campus Student Cafeteria", "Gate 2 Security Office"],
        "location_coords": {
            "Punjab University Central Library": {"lat": 31.4980, "lng": 74.3020},
            "Department of Information Technology": {"lat": 31.4990, "lng": 74.3035},
            "Institute of Business Administration": {"lat": 31.4975, "lng": 74.3010},
            "New Campus Student Cafeteria": {"lat": 31.4985, "lng": 74.3040},
            "Gate 2 Security Office": {"lat": 31.4960, "lng": 74.3000}
        },
        "created_at": three_days_ago,
    }
    pu_id = db.universities.insert_one(pu).inserted_id

    # PU Users
    db.users.insert_one({
        "university_id": pu_id,
        "name": "Prof. Dr. Khalid Mahmood (Registrar Admin)",
        "email": "admin@pu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "admin",
        "status": "active",
        "created_at": three_days_ago,
    })

    pu_student_id = db.users.insert_one({
        "university_id": pu_id,
        "name": "Bilal Hassan",
        "email": "bilal.hassan@pu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "student",
        "status": "active",
        "phone": "+92 312 8889900",
        "created_at": three_days_ago,
    }).inserted_id

    db.users.insert_one({
        "university_id": pu_id,
        "name": "Dr. Saima Rauf",
        "email": "saima.rauf@pu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "teacher",
        "status": "active",
        "phone": "+92 313 8881122",
        "created_at": three_days_ago,
    })

    db.users.insert_one({
        "university_id": pu_id,
        "name": "Muhammad Rafiq (Gate 2 Security Officer)",
        "email": "security@pu.edu.pk",
        "password_hash": hashed_pwd,
        "role": "staff",
        "status": "active",
        "phone": "+92 314 8883344",
        "created_at": three_days_ago,
    })

    # PU Lost Item
    db.reports.insert_one({
        "university_id": pu_id,
        "reporter_id": pu_student_id,
        "reporter_name": "Bilal Hassan",
        "reporter_email": "bilal.hassan@pu.edu.pk",
        "reporter_role": "student",
        "type": "lost",
        "title": "Vintage Brown Leather Fossil Bifold Wallet",
        "description": "Lost in the Central Library ground floor newspaper reading section. Contains student card and CNIC.",
        "category": "Wallet",
        "location": "Punjab University Central Library",
        "lat": 31.4980,
        "lng": 74.3020,
        "date": yesterday.strftime("%Y-%m-%d"),
        "image_url": "https://images.unsplash.com/photo-1627123424574-724758594e93?w=800&auto=format&fit=crop&q=80",
        "status": "open",
        "created_at": yesterday,
    })

    print("[FindIt DB] Pakistani universities and records seeded successfully.")
