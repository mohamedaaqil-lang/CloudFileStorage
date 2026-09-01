"""
File Service Module
Handles File Upload, Storage (Firebase Cloud Storage & Local Fallback),
Metadata Persistence (Cloud Firestore & SQLite), Download, Deletion, Sharing, and Search.
"""

import os
import gc
import time
import uuid
import mimetypes
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.utils import secure_filename

from firebase_config import is_firebase_active, get_firestore, get_storage_bucket
from services.auth_service import DB_FILE

logger = logging.getLogger("FileService")

# Local upload directory setup
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Maximum allowed file size in bytes (50 MB default)
MAX_FILE_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")) * 1024 * 1024

# Allowed file extensions categories
CATEGORY_MAPPING = {
    "pdf": ["pdf"],
    "image": ["jpg", "jpeg", "png", "gif", "svg", "webp", "bmp", "ico", "tiff"],
    "document": ["doc", "docx", "txt", "rtf", "odt", "xls", "xlsx", "csv", "ppt", "pptx", "md", "json", "xml"],
    "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    "video": ["mp4", "webm", "mkv", "avi", "mov", "wmv", "flv"],
    "audio": ["mp3", "wav", "ogg", "flac", "m4a", "aac"]
}

def format_file_size(size_bytes: int) -> str:
    """Formats bytes into a readable string (e.g., KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def get_file_category(extension: str, mimetype: str) -> str:
    """Detects file category based on extension and mime type."""
    ext = extension.lower().lstrip(".")
    for cat, extensions in CATEGORY_MAPPING.items():
        if ext in extensions:
            return cat
    
    if mimetype:
        if mimetype.startswith("image/"):
            return "image"
        elif mimetype == "application/pdf":
            return "pdf"
        elif mimetype.startswith("video/"):
            return "video"
        elif mimetype.startswith("audio/"):
            return "audio"
        elif "word" in mimetype or "sheet" in mimetype or "presentation" in mimetype or "text" in mimetype:
            return "document"
        elif "zip" in mimetype or "compressed" in mimetype or "archive" in mimetype:
            return "archive"
            
    return "other"

def upload_file(user_id: str, file_obj, base_url: str) -> dict:
    """
    Saves uploaded file to Firebase Storage (or local disk) and persists metadata in Firestore/SQLite.
    """
    if not file_obj or file_obj.filename == "":
        return {"success": False, "error": "No file selected for upload."}

    original_filename = file_obj.filename
    safe_filename = secure_filename(original_filename)
    if not safe_filename:
        safe_filename = f"file_{uuid.uuid4().hex[:8]}"

    # Read content length / size
    file_obj.seek(0, os.SEEK_END)
    file_size = file_obj.tell()
    file_obj.seek(0)

    if file_size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        return {"success": False, "error": f"File exceeds maximum allowed size of {max_mb} MB."}

    if file_size == 0:
        return {"success": False, "error": "File is empty (0 bytes)."}

    # File identification
    file_id = str(uuid.uuid4())
    _, ext = os.path.splitext(original_filename)
    mimetype = file_obj.mimetype or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    category = get_file_category(ext, mimetype)
    upload_date = datetime.now(timezone.utc).isoformat()
    formatted_size = format_file_size(file_size)
    storage_path = f"users/{user_id}/{file_id}_{safe_filename}"
    shared_link = f"{base_url.rstrip('/')}/shared/{file_id}"
    storage_url = ""

    # 1. Store in Firebase Cloud Storage + Firestore if active
    if is_firebase_active():
        try:
            bucket = get_storage_bucket()
            db = get_firestore()

            if bucket:
                blob = bucket.blob(storage_path)
                blob.content_type = mimetype
                blob.upload_from_file(file_obj, content_type=mimetype)
                
                try:
                    blob.make_public()
                    storage_url = blob.public_url
                except Exception:
                    storage_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{storage_path.replace('/', '%2F')}?alt=media"

            file_metadata = {
                "file_id": file_id,
                "user_id": user_id,
                "file_name": original_filename,
                "file_type": mimetype,
                "file_size": file_size,
                "file_size_formatted": formatted_size,
                "category": category,
                "upload_date": upload_date,
                "storage_url": storage_url,
                "storage_path": storage_path,
                "shared_link": shared_link,
                "is_public": False
            }

            if db:
                db.collection("files").document(file_id).set(file_metadata)

            logger.info(f"File uploaded to Firebase successfully: {original_filename} (ID: {file_id})")
            return {
                "success": True,
                "message": "File uploaded successfully to cloud storage!",
                "file": file_metadata
            }
        except Exception as e:
            logger.error(f"Firebase Storage upload failed: {e}. Falling back to local disk storage.")

    # 2. Local Fallback Storage
    try:
        user_dir = UPLOADS_DIR / "users" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        local_filepath = user_dir / f"{file_id}_{safe_filename}"
        
        file_obj.seek(0)
        file_obj.save(str(local_filepath))

        storage_url = f"{base_url.rstrip('/')}/download/{file_id}"

        file_metadata = {
            "file_id": file_id,
            "user_id": user_id,
            "file_name": original_filename,
            "file_type": mimetype,
            "file_size": file_size,
            "file_size_formatted": formatted_size,
            "category": category,
            "upload_date": upload_date,
            "storage_url": storage_url,
            "storage_path": str(local_filepath),
            "shared_link": shared_link,
            "is_public": 0
        }

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO files (
                file_id, user_id, file_name, file_type, file_size,
                file_size_formatted, category, upload_date, storage_url,
                storage_path, shared_link, is_public
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, user_id, original_filename, mimetype, file_size,
            formatted_size, category, upload_date, storage_url,
            str(local_filepath), shared_link, 0
        ))
        
        # Update user's total storage
        cursor.execute("""
            UPDATE users SET total_storage_used = total_storage_used + ?
            WHERE user_id = ?
        """, (file_size, user_id))

        conn.commit()
        conn.close()

        logger.info(f"File uploaded to local storage successfully: {original_filename} (ID: {file_id})")
        return {
            "success": True,
            "message": "File uploaded successfully!",
            "file": file_metadata
        }
    except Exception as e:
        logger.error(f"Local file upload failed: {e}")
        return {"success": False, "error": f"Upload failed: {str(e)}"}

def get_user_files(user_id: str) -> dict:
    """
    Retrieves all files belonging to a specific user and aggregates storage statistics.
    """
    files_list = []
    total_bytes = 0
    categories_count = {"pdf": 0, "image": 0, "document": 0, "archive": 0, "video": 0, "audio": 0, "other": 0}

    # 1. Try Firebase Firestore
    if is_firebase_active():
        try:
            db = get_firestore()
            if db:
                docs = db.collection("files").where("user_id", "==", user_id).stream()
                for doc in docs:
                    data = doc.to_dict()
                    files_list.append(data)
                    size = data.get("file_size", 0)
                    total_bytes += size
                    cat = data.get("category", "other")
                    categories_count[cat] = categories_count.get(cat, 0) + 1

                # Sort by upload_date descending
                files_list.sort(key=lambda x: x.get("upload_date", ""), reverse=True)

                return {
                    "success": True,
                    "files": files_list,
                    "stats": {
                        "total_files": len(files_list),
                        "total_bytes": total_bytes,
                        "total_formatted": format_file_size(total_bytes),
                        "categories": categories_count
                    }
                }
        except Exception as e:
            logger.error(f"Firestore get_user_files error: {e}")

    # 2. Local SQLite DB
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE user_id = ? ORDER BY upload_date DESC", (user_id,))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            f = dict(row)
            f["is_public"] = bool(f.get("is_public", 0))
            files_list.append(f)
            size = f.get("file_size", 0)
            total_bytes += size
            cat = f.get("category", "other")
            categories_count[cat] = categories_count.get(cat, 0) + 1

        return {
            "success": True,
            "files": files_list,
            "stats": {
                "total_files": len(files_list),
                "total_bytes": total_bytes,
                "total_formatted": format_file_size(total_bytes),
                "categories": categories_count
            }
        }
    except Exception as e:
        logger.error(f"Local get_user_files error: {e}")
        return {"success": False, "error": f"Failed to retrieve files: {str(e)}"}

def get_file_metadata(file_id: str, user_id: str = None) -> dict:
    """
    Retrieves metadata for a specific file.
    If user_id is provided, enforces that the file belongs to that user.
    """
    # 1. Firestore
    if is_firebase_active():
        try:
            db = get_firestore()
            if db:
                doc = db.collection("files").document(file_id).get()
                if doc.exists:
                    data = doc.to_dict()
                    if user_id and data.get("user_id") != user_id:
                        return None  # Access unauthorized
                    return data
        except Exception as e:
            logger.error(f"Firestore get_file_metadata error: {e}")

    # 2. SQLite
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if user_id:
            cursor.execute("SELECT * FROM files WHERE file_id = ? AND user_id = ?", (file_id, user_id))
        else:
            cursor.execute("SELECT * FROM files WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            f = dict(row)
            f["is_public"] = bool(f.get("is_public", 0))
            return f
        return None
    except Exception as e:
        logger.error(f"SQLite get_file_metadata error: {e}")
        return None

def delete_file(file_id: str, user_id: str) -> dict:
    """
    Permanently deletes a file from Storage and removes metadata from Firestore/SQLite.
    """
    file_info = get_file_metadata(file_id, user_id)
    if not file_info:
        return {"success": False, "error": "File not found or unauthorized."}

    # 1. Firebase Deletion
    if is_firebase_active():
        try:
            bucket = get_storage_bucket()
            db = get_firestore()

            if bucket and file_info.get("storage_path"):
                blob = bucket.blob(file_info["storage_path"])
                if blob.exists():
                    blob.delete()

            if db:
                db.collection("files").document(file_id).delete()

            logger.info(f"File deleted from Firebase: {file_id}")
            return {"success": True, "message": "File deleted successfully from cloud storage!"}
        except Exception as e:
            logger.error(f"Firebase file deletion error: {e}")

    # 2. Local Deletion
    try:
        storage_path = file_info.get("storage_path", "")
        if storage_path and os.path.exists(storage_path):
            gc.collect()  # Release open file handles if any
            try:
                os.remove(storage_path)
            except Exception as file_err:
                logger.warning(f"Could not immediately unlink local file ({file_err}), proceeding with DB cleanup.")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE file_id = ? AND user_id = ?", (file_id, user_id))
        
        # Decrement user total storage used
        file_size = file_info.get("file_size", 0)
        cursor.execute("""
            UPDATE users SET total_storage_used = MAX(0, total_storage_used - ?)
            WHERE user_id = ?
        """, (file_size, user_id))

        conn.commit()
        conn.close()

        logger.info(f"File deleted from local storage: {file_id}")
        return {"success": True, "message": "File deleted successfully!"}
    except Exception as e:
        logger.error(f"Local file deletion error: {e}")
        return {"success": False, "error": f"Failed to delete file: {str(e)}"}

def generate_share_link(file_id: str, user_id: str, base_url: str) -> dict:
    """
    Generates a shareable link and marks file as public.
    """
    file_info = get_file_metadata(file_id, user_id)
    if not file_info:
        return {"success": False, "error": "File not found or unauthorized."}

    share_url = f"{base_url.rstrip('/')}/shared/{file_id}"

    # 1. Update in Firestore
    if is_firebase_active():
        try:
            db = get_firestore()
            if db:
                db.collection("files").document(file_id).update({
                    "shared_link": share_url,
                    "is_public": True
                })
                return {
                    "success": True,
                    "message": "Share link generated successfully!",
                    "shared_link": share_url
                }
        except Exception as e:
            logger.error(f"Firestore share update error: {e}")

    # 2. Update in SQLite
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE files SET shared_link = ?, is_public = 1
            WHERE file_id = ? AND user_id = ?
        """, (share_url, file_id, user_id))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "message": "Share link generated successfully!",
            "shared_link": share_url
        }
    except Exception as e:
        logger.error(f"SQLite share update error: {e}")
        return {"success": False, "error": f"Failed to generate share link: {str(e)}"}

def search_files(user_id: str, query: str = "", category: str = "all") -> dict:
    """
    Searches user's files by query string in file_name and category filter.
    """
    res = get_user_files(user_id)
    if not res.get("success"):
        return res

    all_files = res.get("files", [])
    query = (query or "").strip().lower()
    category = (category or "all").strip().lower()

    filtered = []
    for f in all_files:
        name_match = query in f.get("file_name", "").lower() if query else True
        cat_match = (category == "all") or (f.get("category", "").lower() == category)
        if name_match and cat_match:
            filtered.append(f)

    return {
        "success": True,
        "files": filtered,
        "total_results": len(filtered),
        "query": query,
        "category": category
    }

def get_shared_file_info(file_id: str) -> dict:
    """
    Retrieves public file metadata for guest/shared link view.
    """
    file_info = get_file_metadata(file_id, user_id=None)
    if not file_info:
        return {"success": False, "error": "File not found or the link has expired."}

    return {
        "success": True,
        "file": {
            "file_id": file_info.get("file_id"),
            "file_name": file_info.get("file_name"),
            "file_type": file_info.get("file_type"),
            "file_size_formatted": file_info.get("file_size_formatted"),
            "category": file_info.get("category"),
            "upload_date": file_info.get("upload_date"),
            "storage_url": file_info.get("storage_url"),
            "shared_link": file_info.get("shared_link")
        }
    }
