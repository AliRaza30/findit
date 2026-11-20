import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "findit")
    CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Naye university workspace ke liye default (admin baad mein badal sakta hai)
    DEFAULT_CATEGORIES = ["Wallet", "Electronics", "Documents", "Keys", "Bags", "Clothing", "Other"]
    DEFAULT_LOCATIONS = ["Library", "Cafeteria", "Parking", "Main Gate", "Classroom Block"]
