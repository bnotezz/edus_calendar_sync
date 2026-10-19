import unittest
from datetime import date
from unittest.mock import MagicMock, patch
from googleapiclient.errors import HttpError
import httplib2

from calendar_client import GoogleCalendarClient


class TestGoogleCalendarClient(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.client = GoogleCalendarClient(
            calendar_id="test_calendar@group.calendar.google.com",
            service=self.mock_service,
            rate_limit_delay=0
        )

    def test_init_validation(self):
        with self.assertRaises(ValueError):
            GoogleCalendarClient(calendar_id="cal-id", credentials_info=None, service=None)

    def test_upsert_event_insert_success(self):
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"id": "sch001"}
        self.mock_service.events().insert.return_value = mock_insert

        res = self.client.upsert_event("sch001", "Math", "Teacher", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
        self.assertEqual(res["id"], "sch001")
        self.mock_service.events().insert.assert_called_once()
        self.mock_service.events().update.assert_not_called()

    def test_upsert_event_conflict_fallback(self):
        resp_409 = httplib2.Response({"status": 409})
        error_409 = HttpError(resp_409, b'{"error": "conflict"}')

        mock_insert = MagicMock()
        mock_insert.execute.side_effect = error_409
        self.mock_service.events().insert.return_value = mock_insert

        mock_update = MagicMock()
        mock_update.execute.return_value = {"id": "sch001", "updated": True}
        self.mock_service.events().update.return_value = mock_update

        res = self.client.upsert_event("sch001", "Math", "Teacher", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
        self.assertEqual(res["id"], "sch001")
        self.mock_service.events().insert.assert_called_once()
        self.mock_service.events().update.assert_called_once()

    def test_upsert_event_rate_limit_retry_and_exhaustion(self):
        resp_429 = httplib2.Response({"status": 429})
        error_429 = HttpError(resp_429, b'{"error": "rate limit"}')

        mock_insert = MagicMock()
        mock_insert.execute.side_effect = [error_429, error_429, {"id": "sch001"}]
        self.mock_service.events().insert.return_value = mock_insert

        with patch("time.sleep") as mock_sleep:
            self.client.upsert_event("sch001", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")
            self.assertEqual(mock_insert.execute.call_count, 3)
            self.assertEqual(mock_sleep.call_count, 2)

        # Exhaust retries
        mock_insert.execute.side_effect = error_429
        with patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                self.client.upsert_event("sch001", "Title", "Desc", "2026-10-20T09:00:00", "2026-10-20T09:45:00")

    def test_delete_event(self):
        mock_del = MagicMock()
        mock_del.execute.return_value = {}
        self.mock_service.events().delete.return_value = mock_del

        # Success
        success = self.client.delete_event("sch001")
        self.assertTrue(success)

        # Error
        resp_404 = httplib2.Response({"status": 404})
        mock_del.execute.side_effect = HttpError(resp_404, b'{"error": "not found"}')
        failed = self.client.delete_event("sch999")
        self.assertFalse(failed)

    def test_list_events(self):
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": [{"id": "1"}, {"id": "2"}]}
        self.mock_service.events().list.return_value = mock_list

        items = self.client.list_events("2026-10-20T00:00:00+03:00", "2026-10-27T23:59:59+03:00")
        self.assertEqual(len(items), 2)

    def test_cleanup_events(self):
        events = [
            {"id": "sch20261020n1"},  # active, keep
            {"id": "sch20261020n2"},  # obsolete, delete
            {"id": "hol_summer"}      # non-sch prefix, keep
        ]
        self.client.list_events = MagicMock(return_value=events)
        self.client.delete_event = MagicMock(return_value=True)

        deleted = self.client.cleanup_events(
            start_date=date(2026, 10, 20),
            end_date=date(2026, 10, 27),
            active_ids={"sch20261020n1"},
            prefix="sch"
        )
        self.assertEqual(deleted, 1)
        self.client.delete_event.assert_called_once_with("sch20261020n2")


if __name__ == "__main__":
    unittest.main()
