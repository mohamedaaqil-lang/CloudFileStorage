"""
Cloud-Based File Storage and Sharing System - Backend Application
Flask REST API Server with Firebase Authentication, Cloud Storage, and Firestore.
"""

import os
import io
import sys
import logging
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory, send_file, redirect, g
from flask_cors import CORS
from dotenv import load_dotenv

# Ensure the backend directory is in the Python path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Load .env file
load_dotenv(backend_dir / ".env")

# Import services and configs
from firebase_config import is_firebase_active, init_firebase, FIREBASE_AVAILABLE
from services.auth_service import signup_user, login_user, token_required, verify_token
from services.file_service import (
    upload_file, get_user_files, get_file_metadata,
    delete_file, generate_share_link, search_files, get_shared_file_info
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s")
logger = logging.getLogger("App")

# Initialize Flask app
frontend_dir = backend_dir.parent / "frontend"
app = Flask(
    __name__,
    static_folder=str(frontend_dir),
    static_url_path="",
    template_folder=str(frontend_dir)
)

# Enable CORS for cross-origin requests
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# App configuration
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "cloud_file_storage_secret_key_2026_production_ready")
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024


# ====================================================================
# Frontend UI Page Routes (Direct browser navigation)
# ====================================================================

@app.route("/")
def home():
    """Serves the Landing / Home Page."""
    return send_from_directory(str(frontend_dir), "index.html")

@app.route("/login")
def login_page():
    """Serves the User Login Page."""
    return send_from_directory(str(frontend_dir), "login.html")

@app.route("/signup")
def signup_page():
    """Serves the User Signup Page."""
    return send_from_directory(str(frontend_dir), "signup.html")

@app.route("/dashboard")
def dashboard_page():
    """Serves the User Dashboard Page."""
    return send_from_directory(str(frontend_dir), "dashboard.html")

@app.route("/shared/<file_id>")
def shared_file_view(file_id):
    """Serves the Public Shared File Preview & Download Page."""
    # If it's an API request with Accept: application/json, return JSON
    if request.headers.get("Accept") == "application/json":
        info = get_shared_file_info(file_id)
        if not info.get("success"):
            return jsonify(info), 404
        return jsonify(info), 200
    
    # Otherwise render dashboard or public share template
    return send_from_directory(str(frontend_dir), "dashboard.html")


# ====================================================================
# Authentication REST API Endpoints
# ====================================================================

@app.route("/api/status", methods=["GET"])
@app.route("/api/health", methods=["GET"])
def system_status():
    """Returns the current backend status and Firebase connection state."""
    return jsonify({
        "status": "healthy",
        "firebase_active": is_firebase_active(),
        "mode": "Firebase Cloud Services" if is_firebase_active() else "Local Fallback Development Mode",
        "message": "Cloud-Based File Storage System API is running smoothly."
    }), 200

@app.route("/signup", methods=["POST"])
def signup():
    """
    POST /signup
    Registers a new user with Name, Email, and Password.
    Expected JSON: { "name": "...", "email": "...", "password": "..." }
    """
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not name or not email or not password:
        return jsonify({"success": False, "error": "All fields (name, email, password) are required."}), 400

    result = signup_user(name, email, password)
    status_code = 201 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/login", methods=["POST"])
def login():
    """
    POST /login
    Authenticates user and returns an authorization token.
    Expected JSON: { "email": "...", "password": "..." }
    """
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    result = login_user(email, password)
    status_code = 200 if result.get("success") else 401
    return jsonify(result), status_code

@app.route("/logout", methods=["POST"])
def logout():
    """
    POST /logout
    Handles user logout.
    """
    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    }), 200


# ====================================================================
# File Management REST API Endpoints (Protected by User Auth)
# ====================================================================

@app.route("/upload", methods=["POST"])
@token_required
def upload():
    """
    POST /upload
    Uploads a file to Cloud Storage / Local Storage and saves metadata.
    Enforces user isolation: files are attached to the logged-in user.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in the request."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected."}), 400

    user_id = g.current_user["user_id"]
    base_url = request.host_url.rstrip("/")

    result = upload_file(user_id, file, base_url)
    status_code = 201 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/files", methods=["GET"])
@token_required
def list_files():
    """
    GET /files
    Returns a list of all files uploaded by the authenticated user
    along with aggregate storage usage metrics.
    """
    user_id = g.current_user["user_id"]
    result = get_user_files(user_id)
    status_code = 200 if result.get("success") else 500
    return jsonify(result), status_code

@app.route("/search", methods=["GET"])
@token_required
def search():
    """
    GET /search?q=<query>&category=<category>
    Searches user's files by filename and category.
    """
    user_id = g.current_user["user_id"]
    query = request.args.get("q", "")
    category = request.args.get("category", "all")

    result = search_files(user_id, query, category)
    return jsonify(result), 200

@app.route("/download/<file_id>", methods=["GET"])
def download(file_id):
    """
    GET /download/<file_id>
    Downloads the requested file.
    Permits download if the user is authenticated and owns the file OR if the file is shared.
    """
    # 1. Check if token was provided in header or query param
    auth_header = request.headers.get("Authorization")
    token = request.args.get("token")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    current_user_id = None
    if token:
        ver = verify_token(token)
        if ver.get("valid"):
            current_user_id = ver["user"]["user_id"]

    # 2. Retrieve metadata
    meta = get_file_metadata(file_id)
    if not meta:
        return jsonify({"success": False, "error": "File not found."}), 404

    # 3. Authorization check: must own file OR file is marked public
    is_owner = (current_user_id and current_user_id == meta.get("user_id"))
    is_public = bool(meta.get("is_public"))

    if not is_owner and not is_public:
        return jsonify({"success": False, "error": "Unauthorized access to this file."}), 403

    # 4. Handle download delivery
    storage_path = meta.get("storage_path", "")
    file_name = meta.get("file_name", "download")
    mimetype = meta.get("file_type", "application/octet-stream")

    # If Firebase Storage URL is available
    if is_firebase_active() and meta.get("storage_url") and not os.path.exists(storage_path):
        return redirect(meta["storage_url"])

    # If local file exists
    if storage_path and os.path.exists(storage_path):
        return send_file(
            storage_path,
            as_attachment=True,
            download_name=file_name,
            mimetype=mimetype
        )

    return jsonify({"success": False, "error": "File content could not be located on storage."}), 404

@app.route("/delete/<file_id>", methods=["DELETE", "POST"])
@token_required
def delete(file_id):
    """
    DELETE /delete/<file_id>
    Permanently deletes a file from Storage and Firestore.
    """
    user_id = g.current_user["user_id"]
    result = delete_file(file_id, user_id)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/share/<file_id>", methods=["POST"])
@token_required
def share(file_id):
    """
    POST /share/<file_id>
    Generates a public shareable URL for the specified file.
    """
    user_id = g.current_user["user_id"]
    base_url = request.host_url.rstrip("/")

    result = generate_share_link(file_id, user_id, base_url)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@app.route("/api/shared/<file_id>", methods=["GET"])
def get_shared_details(file_id):
    """
    GET /api/shared/<file_id>
    Returns public file details for guests who have the shareable link.
    """
    result = get_shared_file_info(file_id)
    status_code = 200 if result.get("success") else 404
    return jsonify(result), status_code


# ====================================================================
# Global Error Handlers
# ====================================================================

@app.errorhandler(413)
def request_entity_too_large(error):
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    return jsonify({"success": False, "error": f"File exceeds maximum upload limit of {max_mb} MB."}), 413

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith(("/api", "/upload", "/files", "/download", "/delete", "/share", "/search")):
        return jsonify({"success": False, "error": "API route not found."}), 404
    # For web page 404s, redirect to index
    return send_from_directory(str(frontend_dir), "index.html")

@app.errorhandler(500)
def server_error(error):
    return jsonify({"success": False, "error": "An internal server error occurred."}), 500


# ====================================================================
# Server Entrypoint
# ====================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") == "development"
    
    print("\n" + "=" * 65)
    print("   CLOUD-BASED FILE STORAGE AND SHARING SYSTEM ")
    print("=" * 65)
    print(f" * Server running on: http://127.0.0.1:{port}")
    print(f" * Mode: {'Firebase Live Cloud Services' if is_firebase_active() else 'Local Fallback Development Mode'}")
    print(f" * Frontend UI: http://127.0.0.1:{port}/")
    print("=" * 65 + "\n")
    
    app.run(host="0.0.0.0", port=port, debug=debug)
