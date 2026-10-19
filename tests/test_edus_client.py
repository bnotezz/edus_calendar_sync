import unittest
from unittest.mock import MagicMock
import requests

from edus_client import EdusClient


class TestEdusClient(unittest.TestCase):
    def setUp(self):
        self.mock_session = MagicMock(spec=requests.Session)
        self.client = EdusClient(
            host="https://demo.edus.school/",
            token="initial_jwt_token",
            session=self.mock_session,
            timeout=(5, 15)
        )

    def test_init_and_properties(self):
        self.assertEqual(self.client.host, "https://demo.edus.school")
        self.assertEqual(self.client.token, "initial_jwt_token")
        self.assertEqual(self.client.headers["Authorization"], "Bearer initial_jwt_token")

        self.client.set_token("new_jwt_token")
        self.assertEqual(self.client.token, "new_jwt_token")
        self.assertEqual(self.client.headers["Authorization"], "Bearer new_jwt_token")

        # Test without token
        client_no_token = EdusClient(host="https://demo.edus.school")
        self.assertNotIn("Authorization", client_no_token.headers)

    def test_build_url(self):
        url1 = self.client._build_url("school/settings/general/")
        self.assertEqual(url1, "https://demo.edus.school/api/v1/school/settings/general/")

        url2 = self.client._build_url("/api/v1/custom/endpoint/")
        self.assertEqual(url2, "https://demo.edus.school/api/v1/custom/endpoint/")

    def test_login(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access": "jwt_access_123",
            "refresh": "jwt_refresh_456",
            "uuid": "parent_uuid_789"
        }
        self.mock_session.post.return_value = mock_resp

        data = self.client.login("user@example.com", "secretpass")
        self.assertEqual(data["access"], "jwt_access_123")
        self.assertEqual(self.client.token, "jwt_access_123")
        self.mock_session.post.assert_called_once_with(
            "https://demo.edus.school/api/v1/user/login/",
            data={"login": "user@example.com", "password": "secretpass"},
            headers={},
            timeout=(5, 15)
        )

    def test_refresh_access_token(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access": "refreshed_access_abc"}
        self.mock_session.post.return_value = mock_resp

        data = self.client.refresh_access_token("valid_refresh_token")
        self.assertEqual(data["access"], "refreshed_access_abc")
        self.assertEqual(self.client.token, "refreshed_access_abc")
        self.mock_session.post.assert_called_once_with(
            "https://demo.edus.school/api/v1/user/token-refresh/",
            data={"refresh": "valid_refresh_token"},
            timeout=(5, 15)
        )

    def test_get_parent_students(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"user": {"uuid": "child-1"}}]
        self.mock_session.get.return_value = mock_resp

        students = self.client.get_parent_students("parent-uuid-000")
        self.assertEqual(len(students), 1)
        self.mock_session.get.assert_called_once_with(
            "https://demo.edus.school/api/v1/student/parent-student/parent-uuid-000/",
            params=None,
            headers=self.client.headers,
            timeout=(5, 15)
        )

    def test_get_school_location(self):
        def mock_fetch(path, *args, **kwargs):
            if "general" in path:
                return {"name": "Ліцей 'Вільні'"}
            if "contact" in path:
                return {"address": "вул. Франка, 10", "city": "Львів"}
            return {}

        self.client.fetch_data = mock_fetch
        location = self.client.get_school_location()
        self.assertEqual(location, "Ліцей 'Вільні', вул. Франка, 10, Львів")

    def test_get_school_location_empty_and_error(self):
        self.client.fetch_data = lambda path, *a, **k: {}
        self.assertIsNone(self.client.get_school_location())

        def mock_error(*a, **k):
            raise requests.exceptions.RequestException("API error")
        self.client.fetch_data = mock_error
        self.assertIsNone(self.client.get_school_location())

    def test_get_student_lessons(self):
        self.client.fetch_data = MagicMock(return_value=[{"id": 1, "name": "Урок"}])
        lessons = self.client.get_lesson_list("student-uuid-999")
        self.client.fetch_data.assert_called_once_with("student/lesson-list/student-uuid-999/")
        self.assertEqual(len(lessons), 1)

    def test_get_schedule(self):
        self.client.fetch_data = MagicMock(return_value={"schedule": []})
        res = self.client.get_schedule("student-uuid-999", "2026-10-20")
        self.client.fetch_data.assert_called_once_with(
            "schedule/for-user/student-uuid-999/",
            params={"start_date": "2026-10-20"}
        )
        self.assertEqual(res, {"schedule": []})

    def test_get_menu_and_calendar_endpoints(self):
        self.client.fetch_data = MagicMock(return_value={})
        self.client.get_canteen_menu()
        self.client.fetch_data.assert_called_with("kitchen/menu/")

        self.client.get_exclude_days()
        self.client.fetch_data.assert_called_with("school/exclude-day/")

        self.client.get_semesters()
        self.client.fetch_data.assert_called_with("school/year/semester/")


if __name__ == "__main__":
    unittest.main()
