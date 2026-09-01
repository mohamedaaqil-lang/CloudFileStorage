"""
Firebase Configuration and Initialization Module
Handles connection to Firebase Admin SDK (Authentication, Firestore, Storage)
with support for both live Firebase Cloud Services and Local Fallback Development Mode.
"""

import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
logger = logging.getLogger("FirebaseConfig")

# Global instances
firebase_app = None
firestore_db = None
storage_bucket = None
FIREBASE_AVAILABLE = False

# Read settings from environment
SERVICE_ACCOUNT_KEY = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY", "firebase_credentials.json")
STORAGE_BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", "")
FIREBASE_API_KEY = os.getenv("FIREBASE_WEB_API_KEY", "")
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "")
LOCAL_FALLBACK_MODE = os.getenv("LOCAL_FALLBACK_MODE", "true").lower() in ("true", "1", "yes")

def init_firebase():
    """
    Initializes the Firebase Admin SDK using service account credentials.
    Falls back gracefully if credentials are not provided or invalid.
    """
    global firebase_app, firestore_db, storage_bucket, FIREBASE_AVAILABLE

    # Resolve service account key path
    key_path = Path(SERVICE_ACCOUNT_KEY)
    if not key_path.is_absolute():
        key_path = Path(__file__).resolve().parent / SERVICE_ACCOUNT_KEY

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, storage, auth

        if key_path.exists() and key_path.is_file():
            logger.info(f"Loading Firebase credentials from {key_path}...")
            
            cred = credentials.Certificate(str(key_path))
            
            # Configure options
            options = {}
            if STORAGE_BUCKET_NAME:
                options["storageBucket"] = STORAGE_BUCKET_NAME
            if FIREBASE_PROJECT_ID:
                options["projectId"] = FIREBASE_PROJECT_ID

            if not firebase_admin._apps:
                firebase_app = firebase_admin.initialize_app(cred, options)
            else:
                firebase_app = firebase_admin.get_app()

            firestore_db = firestore.client()
            
            if STORAGE_BUCKET_NAME:
                storage_bucket = storage.bucket()
            else:
                try:
                    storage_bucket = storage.bucket()
                except Exception as e:
                    logger.warning(f"Storage bucket not explicitly configured: {e}")
                    storage_bucket = None

            FIREBASE_AVAILABLE = True
            logger.info(">>> Successfully connected to live Firebase Cloud Services (Auth, Firestore, Storage)!")
            return True
        else:
            logger.warning(f"Firebase service account key not found at '{key_path}'. Running in Local Fallback Mode.")
            FIREBASE_AVAILABLE = False
            return False

    except Exception as e:
        logger.warning(f"Could not initialize Firebase Admin SDK: {e}. Switching to Local Fallback Mode.")
        FIREBASE_AVAILABLE = False
        return False

# Initialize on module load
init_firebase()

def get_firestore():
    """Returns the Firestore database client instance or None."""
    return firestore_db

def get_storage_bucket():
    """Returns the Firebase Cloud Storage bucket instance or None."""
    return storage_bucket

def is_firebase_active():
    """Returns True if live Firebase services are successfully initialized."""
    return FIREBASE_AVAILABLE
