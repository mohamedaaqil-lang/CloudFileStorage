"""
Automated Test Suite for Cloud-Based File Storage and Sharing System
Tests Authentication, File Uploads, Search, Sharing, User Isolation, and Deletions.
"""

import sys
import io
import json
import unittest
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app import app
from firebase_config import is_firebase_active

class CloudFileStorageTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        self.user_a_email = "test_alice@cloudvault.local"
        self.user_a_pass = "Password123"
        self.user_a_name = "Alice Test"

        self.user_b_email = "test_bob@cloudvault.local"
        self.user_b_pass = "Password456"
        self.user_b_name = "Bob Test"

    def test_01_system_status(self):
        """Test API health and system status endpoint."""
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("mode", data)
        print(f"[PASS] Status Endpoint verified. Mode: {data['mode']}")

    def test_02_auth_signup_and_login(self):
        """Test user registration and login."""
        # 1. Signup Alice
        res_signup = self.client.post("/signup", json={
            "name": self.user_a_name,
            "email": self.user_a_email,
            "password": self.user_a_pass
        })
        self.assertIn(res_signup.status_code, [201, 400]) # 400 if already created in earlier run
        
        # 2. Login Alice
        res_login = self.client.post("/login", json={
            "email": self.user_a_email,
            "password": self.user_a_pass
        })
        self.assertEqual(res_login.status_code, 200)
        data = res_login.get_json()
        self.assertTrue(data["success"])
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], self.user_a_email)
        print("[PASS] User Signup & Login verified successfully.")

    def test_03_file_lifecycle_and_sharing(self):
        """Test complete file upload, list, search, share, download, and delete flow."""
        # Login to get token
        res_login = self.client.post("/login", json={
            "email": self.user_a_email,
            "password": self.user_a_pass
        })
        token = res_login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Upload Test File
        sample_content = b"CloudVault Automated Test File Content - 2026."
        file_data = {
            "file": (io.BytesIO(sample_content), "project_specs.pdf")
        }
        res_upload = self.client.post("/upload", headers=headers, data=file_data, content_type="multipart/form-data")
        self.assertEqual(res_upload.status_code, 201)
        upload_json = res_upload.get_json()
        self.assertTrue(upload_json["success"])
        file_id = upload_json["file"]["file_id"]
        self.assertEqual(upload_json["file"]["file_name"], "project_specs.pdf")
        self.assertEqual(upload_json["file"]["category"], "pdf")
        print(f"[PASS] File upload verified. File ID: {file_id}")

        # 2. List Files & Check Stats
        res_files = self.client.get("/files", headers=headers)
        self.assertEqual(res_files.status_code, 200)
        files_json = res_files.get_json()
        self.assertTrue(files_json["success"])
        self.assertGreaterEqual(len(files_json["files"]), 1)
        self.assertIn("stats", files_json)
        self.assertGreater(files_json["stats"]["total_bytes"], 0)
        print(f"[PASS] File listing & storage stats verified ({files_json['stats']['total_files']} files).")

        # 3. Search File by Name
        res_search = self.client.get("/search?q=project", headers=headers)
        self.assertEqual(res_search.status_code, 200)
        search_json = res_search.get_json()
        self.assertTrue(search_json["success"])
        self.assertGreaterEqual(search_json["total_results"], 1)
        print(f"[PASS] Search endpoint verified ({search_json['total_results']} result matches).")

        # 4. Generate Public Share Link
        res_share = self.client.post(f"/share/{file_id}", headers=headers)
        self.assertEqual(res_share.status_code, 200)
        share_json = res_share.get_json()
        self.assertTrue(share_json["success"])
        self.assertIn("shared_link", share_json)
        print(f"[PASS] Share link generated: {share_json['shared_link']}")

        # 5. Public Access to Shared File (No Auth Header)
        res_public = self.client.get(f"/api/shared/{file_id}")
        self.assertEqual(res_public.status_code, 200)
        pub_json = res_public.get_json()
        self.assertTrue(pub_json["success"])
        self.assertEqual(pub_json["file"]["file_id"], file_id)
        print("[PASS] Public share link access verified.")

        # 6. Download File with Token
        res_download = self.client.get(f"/download/{file_id}?token={token}")
        self.assertIn(res_download.status_code, [200, 302])
        res_download.close()
        print("[PASS] File download verified.")

        # 7. Delete File
        res_delete = self.client.delete(f"/delete/{file_id}", headers=headers)
        self.assertEqual(res_delete.status_code, 200)
        del_json = res_delete.get_json()
        self.assertTrue(del_json["success"])
        print("[PASS] File deletion verified.")

    def test_04_user_isolation(self):
        """Verify that User B cannot delete or access unshared files of User A."""
        # 1. Register & Login User A
        self.client.post("/signup", json={
            "name": self.user_a_name,
            "email": self.user_a_email,
            "password": self.user_a_pass
        })
        res_a = self.client.post("/login", json={"email": self.user_a_email, "password": self.user_a_pass})
        token_a = res_a.get_json()["token"]

        # 2. Register & Login User B
        self.client.post("/signup", json={
            "name": self.user_b_name,
            "email": self.user_b_email,
            "password": self.user_b_pass
        })
        res_b = self.client.post("/login", json={"email": self.user_b_email, "password": self.user_b_pass})
        token_b = res_b.get_json()["token"]

        # 3. User A uploads a private confidential file
        res_upload = self.client.post("/upload", headers={"Authorization": f"Bearer {token_a}"}, data={
            "file": (io.BytesIO(b"User A Secret File"), "alice_private.docx")
        }, content_type="multipart/form-data")
        file_id_a = res_upload.get_json()["file"]["file_id"]

        # 4. User B attempts to delete User A's file -> MUST BE REJECTED
        res_bad_delete = self.client.delete(f"/delete/{file_id_a}", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(res_bad_delete.status_code, 400)
        print("[PASS] User isolation verified: User B blocked from deleting User A's file.")

        # Clean up User A's file
        self.client.delete(f"/delete/{file_id_a}", headers={"Authorization": f"Bearer {token_a}"})

if __name__ == "__main__":
    unittest.main()
