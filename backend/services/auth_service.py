"""
Authentication Service Module
Handles User Registration, Login, Token Generation & Verification, and Route Protection.
Supports Firebase Authentication & Firestore alongside Local Secure Fallback Storage.
"""

import os
import re
import time
import json
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import wraps

import jwt
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, jsonify, g

from firebase_config import is_firebase_active, get_firestore, FIREBASE_API_KEY

logger = logging.getLogger("AuthService")

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "cloud_file_storage_secret_key_2026_production_ready")
TOKEN_EXPIRATION_HOURS = 24

# Local DB setup for fallback mode
LOCAL_DB_PATH = Path(__file__).resolve().parent.parent / "data"
LOCAL_DB_PATH.mkdir(parents=True, exist_ok=True)
DB_FILE = LOCAL_DB_PATH / "app_database.sqlite"

def init_local_db():
    """Initializes local SQLite database for offline/fallback storage."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            total_storage_used INTEGER DEFAULT 0
        )
    """)
    
    # Files table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_size_formatted TEXT NOT NULL,
            category TEXT NOT NULL,
            upload_date TEXT NOT NULL,
            storage_url TEXT NOT NULL,
            storage_path TEXT NOT NULL,
            shared_link TEXT,
            is_public INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    conn.commit()
    conn.close()

# Initialize local tables
init_local_db()

def is_valid_email(email: str) -> bool:
    """Validates email format using regex."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))

def generate_jwt_token(user_id: str, email: str, name: str) -> str:
    """Generates a secure JWT token for the user."""
    payload = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def signup_user(name: str, email: str, password: str) -> dict:
    """
    Registers a new user in Firebase Auth + Firestore,
    or falls back to local database.
    """
    # Validation
    if not name or not name.strip():
        return {"success": False, "error": "Name is required."}
    if not email or not is_valid_email(email.strip()):
        return {"success": False, "error": "A valid email address is required."}
    if not password or len(password) < 6:
        return {"success": False, "error": "Password must be at least 6 characters long."}

    name = name.strip()
    email = email.strip().lower()
    created_at = datetime.now(timezone.utc).isoformat()

    if is_firebase_active():
        try:
            from firebase_admin import auth as fb_auth
            # 1. Create user in Firebase Auth
            fb_user = fb_auth.create_user(
                email=email,
                password=password,
                display_name=name
            )
            user_id = fb_user.uid

            # 2. Store user profile in Firestore
            db = get_firestore()
            if db:
                db.collection("users").document(user_id).set({
                    "user_id": user_id,
                    "name": name,
                    "email": email,
                    "created_at": created_at,
                    "total_storage_used": 0
                })

            token = generate_jwt_token(user_id, email, name)
            logger.info(f"Firebase user signed up successfully: {email} (UID: {user_id})")
            return {
                "success": True,
                "message": "User registered successfully in Firebase!",
                "token": token,
                "user": {"user_id": user_id, "name": name, "email": email}
            }

        except Exception as e:
            logger.error(f"Firebase signup error: {e}")
            error_msg = str(e)
            if "EMAIL_EXISTS" in error_msg or "already exists" in error_msg.lower():
                return {"success": False, "error": "An account with this email already exists."}
            return {"success": False, "error": f"Signup failed: {error_msg}"}

    # Fallback to local database
    try:
        import uuid
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check if email exists
        cursor.execute("SELECT user_id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            return {"success": False, "error": "An account with this email already exists."}

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        password_hash = generate_password_hash(password)
        
        cursor.execute("""
            INSERT INTO users (user_id, name, email, password_hash, created_at, total_storage_used)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (user_id, name, email, password_hash, created_at))
        conn.commit()
        conn.close()

        token = generate_jwt_token(user_id, email, name)
        logger.info(f"Local user signed up successfully: {email} (ID: {user_id})")
        return {
            "success": True,
            "message": "User registered successfully!",
            "token": token,
            "user": {"user_id": user_id, "name": name, "email": email}
        }
    except Exception as e:
        logger.error(f"Local signup database error: {e}")
        return {"success": False, "error": f"Failed to register user: {str(e)}"}

def login_user(email: str, password: str) -> dict:
    """
    Authenticates a user with email and password.
    Supports Firebase Auth REST API or local database verification.
    """
    if not email or not password:
        return {"success": False, "error": "Email and password are required."}

    email = email.strip().lower()

    if is_firebase_active():
        # If Firebase Web API Key is provided, use Firebase Auth REST Endpoint
        if FIREBASE_API_KEY and not FIREBASE_API_KEY.startswith("AIzaSyYour"):
            try:
                url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
                payload = {
                    "email": email,
                    "password": password,
                    "returnSecureToken": True
                }
                res = requests.post(url, json=payload, timeout=10)
                data = res.json()

                if res.status_code == 200:
                    user_id = data["localId"]
                    display_name = data.get("displayName") or email.split("@")[0]
                    # Generate app JWT for seamless unified authorization
                    token = generate_jwt_token(user_id, email, display_name)
                    return {
                        "success": True,
                        "message": "Login successful via Firebase!",
                        "token": token,
                        "firebase_id_token": data.get("idToken"),
                        "user": {"user_id": user_id, "name": display_name, "email": email}
                    }
                else:
                    err = data.get("error", {}).get("message", "Invalid email or password.")
                    if "INVALID_LOGIN_CREDENTIALS" in err or "EMAIL_NOT_FOUND" in err or "INVALID_PASSWORD" in err:
                        return {"success": False, "error": "Invalid email or password."}
                    return {"success": False, "error": err}
            except Exception as e:
                logger.error(f"Firebase REST Auth error: {e}")

        # Fallback within Firebase Admin SDK
        try:
            from firebase_admin import auth as fb_auth
            fb_user = fb_auth.get_user_by_email(email)
            user_id = fb_user.uid
            display_name = fb_user.display_name or email.split("@")[0]
            token = generate_jwt_token(user_id, email, display_name)
            return {
                "success": True,
                "message": "Login successful!",
                "token": token,
                "user": {"user_id": user_id, "name": display_name, "email": email}
            }
        except Exception as e:
            logger.warning(f"Firebase Admin lookup failed for {email}: {e}")

    # Fallback to local SQLite database
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user_row = cursor.fetchone()
        conn.close()

        if not user_row or not check_password_hash(user_row["password_hash"], password):
            return {"success": False, "error": "Invalid email or password."}

        token = generate_jwt_token(user_row["user_id"], user_row["email"], user_row["name"])
        return {
            "success": True,
            "message": "Login successful!",
            "token": token,
            "user": {
                "user_id": user_row["user_id"],
                "name": user_row["name"],
                "email": user_row["email"]
            }
        }
    except Exception as e:
        logger.error(f"Local login error: {e}")
        return {"success": False, "error": "An error occurred while logging in."}

def verify_token(token: str) -> dict:
    """Verifies a JWT token or Firebase ID Token and returns the decoded payload."""
    if not token:
        return {"valid": False, "error": "Token is missing."}

    # Clean bearer prefix if present
    if token.startswith("Bearer "):
        token = token[7:].strip()

    # Try JWT decoding
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return {"valid": True, "user": payload}
    except jwt.ExpiredSignatureError:
        return {"valid": False, "error": "Session token has expired. Please log in again."}
    except jwt.InvalidTokenError:
        pass

    # Try Firebase ID Token verification
    if is_firebase_active():
        try:
            from firebase_admin import auth as fb_auth
            decoded = fb_auth.verify_id_token(token)
            return {
                "valid": True,
                "user": {
                    "user_id": decoded["uid"],
                    "email": decoded.get("email", ""),
                    "name": decoded.get("name", "")
                }
            }
        except Exception as e:
            logger.warning(f"Firebase token verification failed: {e}")

    return {"valid": False, "error": "Invalid authentication token."}

def token_required(f):
    """Decorator to enforce user authentication on protected API routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        token = None

        if auth_header:
            parts = auth_header.split(" ")
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
            else:
                token = auth_header

        # Check token query parameter as fallback for download routes
        if not token:
            token = request.args.get("token")

        if not token:
            return jsonify({
                "success": False,
                "error": "Authentication token is required to access this resource."
            }), 401

        verification = verify_token(token)
        if not verification["valid"]:
            return jsonify({
                "success": False,
                "error": verification.get("error", "Unauthorized access.")
            }), 401

        # Store authenticated user in Flask's request context g
        g.current_user = verification["user"]
        return f(*args, **kwargs)

    return decorated
