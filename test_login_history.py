import os
import tempfile
import unittest
import gc


_TEST_DIRECTORY = tempfile.TemporaryDirectory(prefix="weather-login-history-")
_TEST_ORIGIN = "https://login-history-test.vercel.app"
os.environ["FLASK_SECRET_KEY"] = "login-history-tests-only-secret"
os.environ["DATABASE_PATH"] = os.path.join(
    _TEST_DIRECTORY.name,
    "test.db"
)
os.environ["VERCEL_ORIGIN"] = _TEST_ORIGIN

import database
import app as app_module

app = app_module.app


class LoginHistoryTests(unittest.TestCase):
    def setUp(self):
        database.init_db()
        with database.get_connection() as conn:
            conn.execute("DELETE FROM user_login_history")
            conn.execute("DELETE FROM password_reset_otps")
            conn.execute("DELETE FROM users")

        self.admin_id = self._register("Admin Farmer", "9876543210")
        app_module.ADMIN_USER_ID = self.admin_id
        self.origin_headers = {"Origin": _TEST_ORIGIN}

    def _register(self, name, phone):
        success, message, user_id = database.register_user({
            "full_name": name,
            "phone": phone,
            "email": f"{phone}@example.test",
            "password": "FarmPass123",
            "confirm_password": "FarmPass123",
            "latitude": 29.68,
            "longitude": 76.99,
            "state": "Haryana",
            "district": "Karnal",
            "village": "Greenfield",
            "pin_code": "132001",
            "farming_type": "Organic",
            "farm_size": "2.5",
            "crops": "Wheat",
            "soil_type": "Alluvial"
        })
        self.assertTrue(success, message)
        return user_id

    def test_home_shows_admin_login_and_only_shows_dashboard_for_sessions(self):
        client = app.test_client()

        guest_home = client.get("/")
        self.assertEqual(guest_home.status_code, 200)
        self.assertIn(b"Login as admin", guest_home.data)
        self.assertIn(
            b"https://login-history-test.vercel.app/?auth=admin",
            guest_home.data
        )
        self.assertNotIn(b"Open my dashboard", guest_home.data)
        self.assertEqual(client.get("/dashboard").status_code, 302)

        farmer_id = self._register("Regular Farmer", "9876543211")
        with client.session_transaction() as session:
            session["user_id"] = farmer_id
            session["full_name"] = "Regular Farmer"

        signed_in_home = client.get("/")
        self.assertIn(b"Login as admin", signed_in_home.data)
        self.assertIn(b"Open my dashboard", signed_in_home.data)
        self.assertIn(b'id="quickLoginForm"', signed_in_home.data)

    def test_successful_logins_are_saved_and_admin_can_review_them(self):
        client = app.test_client()
        login_payload = {
            "identifier": self.admin_id,
            "password": "FarmPass123"
        }

        failed_login = client.post(
            "/api/auth/login",
            json={"identifier": self.admin_id, "password": "wrong"},
            headers=self.origin_headers
        )
        self.assertEqual(failed_login.status_code, 401)

        first_login = client.post(
            "/api/auth/login",
            json=login_payload,
            headers=self.origin_headers
        )
        self.assertEqual(first_login.status_code, 200)
        self.assertTrue(first_login.get_json()["is_admin"])
        admin_token = first_login.get_json()["access_token"]
        bearer_headers = {
            **self.origin_headers,
            "Authorization": f"Bearer {admin_token}"
        }

        second_login = client.post(
            "/api/auth/login",
            json=login_payload,
            headers=self.origin_headers
        )
        self.assertEqual(second_login.status_code, 200)

        form_login = client.post(
            "/login",
            data={
                "identifier": self.admin_id,
                "password": "FarmPass123"
            }
        )
        self.assertEqual(form_login.status_code, 302)

        admin_form_login = client.post(
            "/login",
            data={
                "identifier": self.admin_id,
                "password": "FarmPass123",
                "login_mode": "admin"
            }
        )
        self.assertEqual(admin_form_login.status_code, 302)
        self.assertEqual(
            admin_form_login.headers["Location"],
            "/admin/farmers"
        )

        with database.get_connection() as conn:
            records = conn.execute("""
                SELECT logged_in_at
                FROM user_login_history
                WHERE user_id = ?
                ORDER BY id
            """, (self.admin_id,)).fetchall()
        self.assertEqual(len(records), 4)
        self.assertTrue(all(record["logged_in_at"].endswith("Z") for record in records))

        farmer_list = client.get(
            "/api/admin/farmers",
            headers=bearer_headers
        )
        self.assertEqual(farmer_list.status_code, 200)
        farmer = farmer_list.get_json()["farmers"][0]
        self.assertEqual(farmer["login_count"], 4)
        self.assertEqual(farmer["last_login_at"], records[-1]["logged_in_at"])

        history = client.get(
            f"/api/admin/farmers/{self.admin_id}/logins",
            headers=bearer_headers
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.get_json()["total"], 4)
        self.assertEqual(len(history.get_json()["logins"]), 4)

        with client.session_transaction() as session:
            session["user_id"] = self.admin_id
        legacy_admin_page = client.get("/admin/farmers")
        self.assertEqual(legacy_admin_page.status_code, 200)
        self.assertIn(b"Login Count", legacy_admin_page.data)
        self.assertIn(b"Last Login (UTC)", legacy_admin_page.data)
        self.assertIn(b">4</td>", legacy_admin_page.data)

    def test_admin_login_rejects_farmer_accounts(self):
        farmer_id = self._register("Regular Farmer", "9876543211")
        client = app.test_client()

        farmer_login = client.post(
            "/api/auth/login",
            json={
                "identifier": farmer_id,
                "password": "FarmPass123"
            },
            headers=self.origin_headers
        )
        self.assertEqual(farmer_login.status_code, 200)
        self.assertFalse(farmer_login.get_json()["is_admin"])

        rejected_login = client.post(
            "/login",
            data={
                "identifier": farmer_id,
                "password": "FarmPass123",
                "login_mode": "admin"
            }
        )
        self.assertEqual(rejected_login.status_code, 403)
        self.assertIn(
            b"does not have administrator access",
            rejected_login.data
        )

        protected_data = client.get(
            "/api/admin/farmers",
            headers={
                **self.origin_headers,
                "Authorization": f"Bearer {farmer_login.get_json()['access_token']}"
            }
        )
        self.assertEqual(protected_data.status_code, 403)

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        _TEST_DIRECTORY.cleanup()


if __name__ == "__main__":
    unittest.main()
