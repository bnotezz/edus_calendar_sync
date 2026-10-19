"""
Client for interacting with the Edus.school REST API.

Provides structured methods for:
- Authentication (login, token refresh)
- Parent and student profile discovery
- School settings and location
- Lesson lists and weekly schedules
- Canteen menus
- Holidays, exclude days, and academic semesters
"""

import logging
import requests

logger = logging.getLogger(__name__)


class EdusClient:
    """Reusable API client for the Edus.school educational platform."""

    def __init__(self, host, token=None, session=None, timeout=(10, 30)):
        """
        Initialize the Edus client.

        :param host: Base URL of the school portal (e.g., 'https://demo.edus.school')
        :param token: Optional JWT Bearer access token
        :param session: Optional requests.Session instance
        :param timeout: Tuple of (connect_timeout, read_timeout) in seconds
        """
        self.host = host.rstrip('/')
        self.token = token
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def headers(self):
        """Constructs request headers including Bearer token if present."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def set_token(self, token):
        """Updates the active access token."""
        self.token = token

    def _build_url(self, path):
        """Builds full URL for an API endpoint under /api/v1/."""
        clean_path = path.lstrip('/')
        if not clean_path.startswith("api/v1/"):
            clean_path = f"api/v1/{clean_path}"
        return f"{self.host}/{clean_path}"

    def request(self, method, path, params=None, data=None, json=None, headers=None, timeout=None):
        """
        Performs an HTTP request to the Edus API.

        :param method: HTTP method ('GET', 'POST', etc.)
        :param path: Endpoint path
        :param params: Query parameters dictionary
        :param data: Form data dictionary
        :param json: JSON body data
        :param headers: Optional custom headers to merge
        :param timeout: Optional override for request timeout
        :return: Decoded JSON response (or response object if not JSON)
        """
        url = self._build_url(path)
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)

        req_timeout = timeout or self.timeout
        method_upper = method.upper()
        if method_upper == "GET":
            response = self.session.get(
                url,
                params=params,
                headers=req_headers,
                timeout=req_timeout
            )
        elif method_upper == "POST":
            response = self.session.post(
                url,
                data=data,
                json=json,
                headers=req_headers,
                timeout=req_timeout
            )
        else:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json,
                headers=req_headers,
                timeout=req_timeout
            )
        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            return response.text

    def fetch_data(self, path, params=None, timeout=None):
        """
        Helper method to perform GET request and display record count.
        Preserves backward compatibility with legacy fetch_data calls.
        """
        data = self.request("GET", path, params=params, timeout=timeout)
        count = 0
        if isinstance(data, dict):
            if 'schedule' in data:
                count = len(data['schedule'])
            elif 'menu' in data:
                count = len(data['menu'])
            elif '1' in data:
                count = len(data['1'])
            elif data:
                count = 1
        elif isinstance(data, list):
            count = len(data)

        print(f"📡 Отримано дані з {path}. Знайдено записів: {count}")
        return data

    # =========================================================================
    # Authentication & User Management
    # =========================================================================

    def login(self, login, password):
        """
        Authenticates a user using credentials.

        :param login: User email or username
        :param password: User password
        :return: Dict with 'access', 'refresh', and 'uuid'
        """
        url = self._build_url("user/login/")
        # Edus login endpoint uses multipart form data / form-encoded data
        headers = {}  # Let requests set multipart or default form boundaries
        response = self.session.post(
            url,
            data={"login": login, "password": password},
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        if "access" in data:
            self.token = data["access"]
        return data

    def refresh_access_token(self, refresh_token):
        """
        Refreshes the access token using a refresh token.

        :param refresh_token: Valid JWT refresh token
        :return: Dict containing new 'access' token
        """
        url = self._build_url("user/token-refresh/")
        response = self.session.post(
            url,
            data={"refresh": refresh_token},
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        if "access" in data:
            self.token = data["access"]
        return data

    def get_parent_students(self, parent_uuid):
        """
        Retrieves list of student profiles linked to a parent account.

        :param parent_uuid: Parent user UUID
        :return: List of student records
        """
        return self.fetch_data(f"student/parent-student/{parent_uuid}/")

    # =========================================================================
    # School Information
    # =========================================================================

    def get_general_settings(self):
        """Retrieves general school information (e.g., name)."""
        return self.fetch_data("school/settings/general/")

    def get_contact_settings(self):
        """Retrieves school contact information (address, city)."""
        return self.fetch_data("school/settings/contact/")

    def get_school_location(self):
        """
        Dynamically fetches and formats school name and address for calendar events.

        :return: Formatted string (e.g., 'Ліцей Вільні, вул. Шевченка 1, Київ') or None
        """
        try:
            general = self.get_general_settings()
            contact = self.get_contact_settings()
        except Exception as e:
            print(f"⚠️ Не вдалося отримати локацію школи: {e}")
            return None

        name = (general.get('name') or '').strip() if isinstance(general, dict) else ''
        address = (contact.get('address') or '').strip() if isinstance(contact, dict) else ''
        city = (contact.get('city') or '').strip() if isinstance(contact, dict) else ''

        parts = [part for part in [name, address, city] if part]
        if not parts:
            print("ℹ️ Локацію школи не знайдено в налаштуваннях")
            return None

        location = ", ".join(parts)
        print(f"📍 Локація для розкладу: {location}")
        return location

    # =========================================================================
    # Lessons, Schedule, Menu, Holidays
    # =========================================================================

    def get_lesson_list(self, user_uuid):
        """
        Retrieves student subject list.

        :param user_uuid: Student UUID
        :return: List of lessons
        """
        print("⏳ Отримання списку уроків...")
        lesson_list = self.fetch_data(f"student/lesson-list/{user_uuid}/")
        print(f"✅ Отримано {len(lesson_list)} уроків.")
        return lesson_list

    def get_schedule(self, user_uuid, start_date):
        """
        Retrieves schedule for a student starting from a given date.

        :param user_uuid: Student UUID
        :param start_date: Starting date string in 'YYYY-MM-DD' format
        :return: Schedule dictionary containing 'schedule' list
        """
        return self.fetch_data(
            f"schedule/for-user/{user_uuid}/",
            params={"start_date": start_date}
        )

    def get_canteen_menu(self):
        """Retrieves the school canteen menu mapping."""
        return self.fetch_data("kitchen/menu/")

    def get_exclude_days(self):
        """Retrieves school exclude/holiday days."""
        return self.fetch_data("school/exclude-day/")

    def get_semesters(self):
        """Retrieves school semester dates."""
        return self.fetch_data("school/year/semester/")
