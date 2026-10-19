import os
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError
import httplib2

from sync import SchoolSync, SUBJECT_EMOJIS, load_dotenv_if_present, main


class TestDotenvLoader(unittest.TestCase):
    def test_load_dotenv_if_present(self):
        temp_env_path = os.path.join(os.path.dirname(__file__), ".env.test_tmp")
        try:
            with open(temp_env_path, "w", encoding="utf-8") as f:
                f.write("# Sample comment\n")
                f.write("TEST_ENV_VAR_EDUS=hello_edus_sync\n")
                f.write("QUOTED_VAR='quoted_value'\n")
                f.write("EMPTY_LINE_FOLLOWS=\n\n")

            with patch("sync.os.path.isfile") as mock_isfile, \
                 patch("builtins.open", unittest.mock.mock_open(read_data=(
                     "# Comment\nTEST_ENV_VAR_EDUS=hello_edus_sync\nQUOTED_VAR='quoted_value'\n"
                 ))):
                mock_isfile.side_effect = lambda p: p.endswith(".env.local")
                if "TEST_ENV_VAR_EDUS" in os.environ:
                    del os.environ["TEST_ENV_VAR_EDUS"]
                load_dotenv_if_present()
                self.assertEqual(os.environ.get("TEST_ENV_VAR_EDUS"), "hello_edus_sync")
                self.assertEqual(os.environ.get("QUOTED_VAR"), "quoted_value")
        finally:
            if "TEST_ENV_VAR_EDUS" in os.environ:
                del os.environ["TEST_ENV_VAR_EDUS"]
            if "QUOTED_VAR" in os.environ:
                del os.environ["QUOTED_VAR"]


class TestSchoolSyncInit(unittest.TestCase):
    def test_init_validation(self):
        with self.assertRaises(ValueError):
            SchoolSync(
                host="https://school.edus.school",
                token="test-token",
                calendar_id="cal-id",
                user_uuid="uuid-123",
                credentials_info=None,
                service=None
            )

    def test_init_with_service(self):
        mock_service = MagicMock()
        sync = SchoolSync(
            host="https://school.edus.school/",
            token="test-token",
            calendar_id="cal-id",
            user_uuid="uuid-123",
            service=mock_service,
            load_location=False
        )
        self.assertEqual(sync.host, "https://school.edus.school")
        self.assertEqual(sync.headers["Authorization"], "Bearer test-token")
        self.assertEqual(sync.calendar_id, "cal-id")
        self.assertEqual(sync.user_uuid, "uuid-123")
        self.assertIs(sync.service, mock_service)
        self.assertIsNone(sync.school_location)


class TestSchoolSyncMethods(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.mock_session = MagicMock()
        self.sync = SchoolSync(
            host="https://school.edus.school",
            token="test-token",
            calendar_id="cal-123",
            user_uuid="uuid-student-456",
            service=self.mock_service,
            session=self.mock_session,
            rate_limit_delay=0,
            load_location=False
        )

    def test_fetch_data_formats(self):
        test_cases = [
            ({"schedule": [1, 2, 3]}, 3),
            ({"menu": [1, 2]}, 2),
            ({"1": [1, 2, 3, 4]}, 4),
            ([1, 2, 3, 4, 5], 5),
            ({"name": "Lyceum"}, 1),
            ({}, 0)
        ]
        for payload, _ in test_cases:
            mock_response = MagicMock()
            mock_response.json.return_value = payload
            self.mock_session.get.return_value = mock_response

            res = self.sync.fetch_data("some/path/")
            self.assertEqual(res, payload)
            self.mock_session.get.assert_called_with(
                "https://school.edus.school/api/v1/some/path/",
                headers=self.sync.headers,
                params=None,
                timeout=(10, 30)
            )

    def test_get_school_location(self):
        # 1. Full location
        def mock_fetch(path, *args, **kwargs):
            if "general" in path:
                return {"name": "Ліцей 'Вільні'"}
            if "contact" in path:
                return {"address": "вул. Героїв 1", "city": "Київ"}
            return {}

        self.sync.fetch_data = mock_fetch
        location = self.sync.get_school_location()
        self.assertEqual(location, "Ліцей 'Вільні', вул. Героїв 1, Київ")

        # 2. Partial location
        self.sync.fetch_data = lambda path, *a, **k: {"name": "Ліцей"} if "general" in path else {}
        self.assertEqual(self.sync.get_school_location(), "Ліцей")

        # 3. Empty location
        self.sync.fetch_data = lambda path, *a, **k: {}
        self.assertIsNone(self.sync.get_school_location())

        # 4. Exception handling
        def mock_error(*a, **k):
            raise ConnectionError("Network error")
        self.sync.fetch_data = mock_error
        self.assertIsNone(self.sync.get_school_location())

    def test_get_lessons_list(self):
        self.sync.fetch_data = MagicMock(return_value=[{"id": 1, "name": "Math"}])
        res = self.sync.get_lessons_list()
        self.sync.fetch_data.assert_called_once_with(f"student/lesson-list/{self.sync.user_uuid}/")
        self.assertEqual(len(res), 1)

    def test_send_telegram_alert(self):
        # Without env vars
        with patch.dict(os.environ, {}, clear=True):
            self.sync.send_telegram_alert("Hello")
            self.mock_session.post.assert_not_called()

        # With env vars
        env = {"TELEGRAM_BOT_TOKEN": "bot123", "TELEGRAM_CHAT_ID": "chat999"}
        with patch.dict(os.environ, env, clear=True):
            self.sync.send_telegram_alert("Alert message")
            self.mock_session.post.assert_called_once_with(
                "https://api.telegram.org/botbot123/sendMessage",
                json={"chat_id": "chat999", "text": "Alert message"},
                timeout=10
            )

    def test_sync_holidays(self):
        today = self.sync.today
        future_start = (today + timedelta(days=5)).strftime("%Y-%m-%d")
        future_end = (today + timedelta(days=10)).strftime("%Y-%m-%d")
        past_start = (today - timedelta(days=15)).strftime("%Y-%m-%d")
        past_end = (today - timedelta(days=10)).strftime("%Y-%m-%d")

        exclude_data = {
            "1": [
                {"id": "autumn-1", "name": "Осінні канікули", "start_day": future_start, "end_day": future_end},
                {"id": "past-1", "name": "Минулі", "start_day": past_start, "end_day": past_end}
            ]
        }
        future_year = today.year if today.month < 6 else today.year + 1
        semesters = [
            {"id": "1", "name": "1", "end_date": f"{today.year}-12-25"},
            {"id": "2", "name": "2", "end_date": f"{future_year}-06-01"}
        ]

        def mock_fetch(path, *args, **kwargs):
            if "exclude-day" in path:
                return exclude_data
            if "semester" in path:
                return semesters
            return {}

        self.sync.fetch_data = mock_fetch
        upsert_calls = []
        self.sync.upsert_event = lambda *args, **kwargs: upsert_calls.append((args, kwargs))

        self.sync.sync_holidays()

        # Past holiday must be skipped, autumn holiday + summer holiday added
        self.assertEqual(len(upsert_calls), 2)
        autumn_call = upsert_calls[0]
        self.assertEqual(autumn_call[0][0], "holautumn1")
        self.assertIn("Осінні канікули", autumn_call[0][1])

        summer_call = upsert_calls[1]
        self.assertEqual(summer_call[0][0], "holsummer2")
        self.assertIn("Літні канікули", summer_call[0][1])

    def test_sync_schedule_flow(self):
        today = self.sync.today
        event_date_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        past_date_str = (today - timedelta(days=2)).strftime("%Y-%m-%d")

        menu_data = {
            "menu": [
                {
                    "week_day": 2,
                    "dishes": [
                        {"event_name": "Обід", "dish": "Борщ український, пампушки"}
                    ]
                }
            ]
        }

        schedule_data = {
            "schedule": [
                {
                    "date": event_date_str,
                    "week_day": 2,
                    "order_num": 1,
                    "start_time": "09:00",
                    "end_time": "09:45",
                    "schedule_object": {"id": 105, "type": "lesson", "name": "Математика"},
                    "user": {"username": "Олена Петрівна"}
                },
                {
                    "date": event_date_str,
                    "week_day": 2,
                    "order_num": None,
                    "start_time": "13:00",
                    "end_time": "13:30",
                    "schedule_object": {"id": 201, "type": "event", "name": "Обід"},
                    "user": {}
                },
                {
                    "date": past_date_str,
                    "week_day": 1,
                    "order_num": 1,
                    "start_time": "09:00",
                    "end_time": "09:45",
                    "schedule_object": {"id": 101, "type": "lesson", "name": "Математика"},
                    "user": {}
                }
            ]
        }

        def mock_fetch(path, *args, **kwargs):
            if "kitchen/menu" in path:
                return menu_data
            if "schedule/for-user" in path:
                return schedule_data
            return {}

        self.sync.fetch_data = mock_fetch
        upserted_events = []
        self.sync.upsert_event = lambda *args, **kwargs: upserted_events.append((args, kwargs))
        self.sync.cleanup_old_events = MagicMock()

        self.sync.sync_schedule_flow()

        # Both current week and next week are fetched (each yields 2 future events)
        self.assertEqual(len(upserted_events), 4)

        # Check math lesson properties
        math_call = upserted_events[0]
        eid, summary, desc, start, end = math_call[0][:5]
        self.assertTrue(eid.startswith("sch"))
        self.assertIn("n1", eid)
        self.assertIn(SUBJECT_EMOJIS["Математика"], summary)
        self.assertIn("Вчитель: Олена Петрівна", desc)
        self.assertEqual(math_call[1]["color_id"], str((105 % 11) + 1))
        self.assertEqual(math_call[1]["extended_properties"]["private"]["edus_object_id"], "105")

        # Check lunch event with menu
        lunch_call = upserted_events[1]
        lunch_eid, lunch_sum, lunch_desc = lunch_call[0][:3]
        self.assertTrue(lunch_eid.startswith("sch"))
        self.assertIn("t1300", lunch_eid)
        self.assertIn("Борщ український", lunch_desc)

        # Ensure cleanup was called
        self.sync.cleanup_old_events.assert_called_once()

    def test_cleanup_old_events(self):
        start_date = date(2026, 10, 19)
        end_date = date(2026, 10, 26)
        active_ids = {"sch20261019n1", "sch20261019n2"}

        mock_events = [
            {"id": "sch20261019n1"},  # active, do not delete
            {"id": "sch20261019n9"},  # old/canceled, must delete
            {"id": "hol_summer"},     # holiday, must NOT delete
            {"id": "sch20261020n3"}   # old/canceled, must delete
        ]

        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": mock_events}
        mock_delete = MagicMock()
        mock_delete.execute.return_value = {}

        self.mock_service.events().list.return_value = mock_list
        self.mock_service.events().delete.return_value = mock_delete

        self.sync.cleanup_old_events(start_date, end_date, active_ids)

        # Should have called delete twice: for sch20261019n9 and sch20261020n3
        self.assertEqual(self.mock_service.events().delete.call_count, 2)
        deleted_ids = [call.kwargs["eventId"] for call in self.mock_service.events().delete.call_args_list]
        self.assertIn("sch20261019n9", deleted_ids)
        self.assertIn("sch20261020n3", deleted_ids)

    def test_upsert_event_insert_success(self):
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"id": "sch123"}
        self.mock_service.events().insert.return_value = mock_insert

        self.sync.upsert_event("sch123", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
        self.mock_service.events().insert.assert_called_once()
        self.mock_service.events().update.assert_not_called()

    def test_upsert_event_conflict_fallback_to_update(self):
        resp_409 = httplib2.Response({"status": 409})
        error_409 = HttpError(resp_409, b'{"error": "already exists"}')

        mock_insert = MagicMock()
        mock_insert.execute.side_effect = error_409
        self.mock_service.events().insert.return_value = mock_insert

        mock_update = MagicMock()
        mock_update.execute.return_value = {"id": "sch123"}
        self.mock_service.events().update.return_value = mock_update

        self.sync.upsert_event("sch123", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
        self.mock_service.events().insert.assert_called_once()
        self.mock_service.events().update.assert_called_once()

    def test_upsert_event_rate_limit_retry(self):
        resp_429 = httplib2.Response({"status": 429})
        error_429 = HttpError(resp_429, b'{"error": "rate limit"}')

        mock_insert = MagicMock()
        # Fail twice with 429, succeed on third attempt
        mock_insert.execute.side_effect = [error_429, error_429, {"id": "sch123"}]
        self.mock_service.events().insert.return_value = mock_insert

        with patch("time.sleep") as mock_sleep:
            self.sync.upsert_event("sch123", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
            self.assertEqual(mock_insert.execute.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)

    def test_upsert_event_exhaust_retries_raises(self):
        resp_429 = httplib2.Response({"status": 429})
        error_429 = HttpError(resp_429, b'{"error": "rate limit"}')

        mock_insert = MagicMock()
        mock_insert.execute.side_effect = error_429
        self.mock_service.events().insert.return_value = mock_insert

        with patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.sync.upsert_event("sch123", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")


class TestMainCLI(unittest.TestCase):
    @patch("sync.load_dotenv_if_present")
    def test_main_missing_env_vars(self, mock_load_dotenv):
        with patch.dict(os.environ, {}, clear=True):
            code = main(["--mode", "schedule"])
            self.assertEqual(code, 1)

    @patch("sync.load_dotenv_if_present")
    def test_main_invalid_json_credentials(self, mock_load_dotenv):
        env = {
            "SCHOOL_HOST": "https://school.edus.school",
            "SCHOOL_TOKEN": "token",
            "SCHOOL_USER_UUID": "uuid",
            "GOOGLE_CALENDAR_ID": "cal-id",
            "GOOGLE_SERVICE_ACCOUNT_JSON": "{invalid_json"
        }
        with patch.dict(os.environ, env, clear=True):
            code = main(["--mode", "schedule"])
            self.assertEqual(code, 1)

    @patch("sync.load_dotenv_if_present")
    @patch("sync.SchoolSync")
    def test_main_schedule_mode_success(self, mock_sync_cls, mock_load_dotenv):
        mock_instance = MagicMock()
        mock_sync_cls.return_value = mock_instance
        env = {
            "SCHOOL_HOST": "https://school.edus.school",
            "SCHOOL_TOKEN": "token",
            "SCHOOL_USER_UUID": "uuid",
            "GOOGLE_CALENDAR_ID": "cal-id",
            "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}'
        }
        with patch.dict(os.environ, env, clear=True):
            code = main(["--mode", "schedule"])
            self.assertEqual(code, 0)
            mock_instance.sync_schedule_flow.assert_called_once()
            mock_instance.sync_holidays.assert_not_called()

    @patch("sync.load_dotenv_if_present")
    @patch("sync.SchoolSync")
    def test_main_holidays_mode_success(self, mock_sync_cls, mock_load_dotenv):
        mock_instance = MagicMock()
        mock_sync_cls.return_value = mock_instance
        env = {
            "SCHOOL_HOST": "https://school.edus.school",
            "SCHOOL_TOKEN": "token",
            "SCHOOL_USER_UUID": "uuid",
            "GOOGLE_CALENDAR_ID": "cal-id",
            "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}'
        }
        with patch.dict(os.environ, env, clear=True):
            code = main(["--mode", "holidays"])
            self.assertEqual(code, 0)
            mock_instance.sync_holidays.assert_called_once()
            mock_instance.sync_schedule_flow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
