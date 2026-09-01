"""
Cloud-Based File Storage and Sharing System - Root Launcher
Delegates directly to backend/app.py for standard developer execution.
"""

import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).resolve().parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app import app, is_firebase_active
import os

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