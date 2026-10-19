"""
Main CLI entry point and high-level orchestrator for Edus Calendar Sync.

Provides:
- Dotenv configuration loading for seamless local execution
- Command-line interface for running schedule or holiday synchronizations
- Backward-compatible SchoolSync coordinator wrapping modular service components
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime

from edus_client import EdusClient
from calendar_client import GoogleCalendarClient
from calendar_mapper import SUBJECT_EMOJIS
from sync_service import SyncService
from notifier import send_telegram_alert

__all__ = ["SchoolSync", "SUBJECT_EMOJIS", "main", "load_dotenv_if_present"]

logger = logging.getLogger(__name__)


def load_dotenv_if_present():
    """Loads environment variables from .env.local or .env if present."""
    for filename in [".env.local", ".env"]:
        filepath = os.path.join(os.path.dirname(__file__), filename)
        if os.path.isfile(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
                break
            except Exception as e:
                print(f"⚠️ Could not load {filename}: {e}")


class SchoolSync:
    """
    High-level synchronization coordinator.
    Delegates domain API calls, calendar operations, and mapping to specialized components.
    """

    def __init__(self, host, token, calendar_id, user_uuid, credentials_info=None,
                 service=None, session=None, rate_limit_delay=0.5, load_location=True,
                 edus_client=None, calendar_client=None, today=None):
        self.host = host.rstrip('/')
        self.calendar_id = calendar_id
        self.user_uuid = user_uuid
        self.rate_limit_delay = rate_limit_delay
        self.today = today or datetime.now().date()

        # 1. Edus API Client component
        self.edus = edus_client or EdusClient(
            host=self.host,
            token=token,
            session=session
        )
        self.session = self.edus.session
        self.headers = self.edus.headers

        # 2. Google Calendar API Client component
        self.calendar = calendar_client or GoogleCalendarClient(
            calendar_id=calendar_id,
            credentials_info=credentials_info,
            service=service,
            rate_limit_delay=rate_limit_delay
        )
        self.service = self.calendar.service

        # 3. Synchronizer Service orchestrator
        self.sync_service = SyncService(
            edus_client=self.edus,
            calendar_client=self.calendar,
            user_uuid=user_uuid,
            today=self.today,
            load_location=load_location
        )
        self.school_location = self.sync_service.school_location

    @property
    def fetch_data(self):
        """Delegates data fetching to EdusClient."""
        return self.edus.fetch_data

    @fetch_data.setter
    def fetch_data(self, func):
        self.edus.fetch_data = func

    def get_school_location(self):
        """Delegates school location fetching to EdusClient."""
        return self.edus.get_school_location()

    def get_lessons_list(self):
        """Delegates lesson listing to EdusClient."""
        return self.edus.get_lesson_list(self.user_uuid)

    def sync_holidays(self):
        """Executes the holiday sync step."""
        return self.sync_service.sync_holidays()

    def sync_schedule_flow(self, weeks_ahead=1):
        """Executes the schedule sync step."""
        return self.sync_service.sync_schedule(weeks_ahead=weeks_ahead)

    @property
    def upsert_event(self):
        """Delegates event upsert to GoogleCalendarClient."""
        return self.calendar.upsert_event

    @upsert_event.setter
    def upsert_event(self, func):
        self.calendar.upsert_event = func

    @property
    def cleanup_old_events(self):
        """Delegates event cleanup to GoogleCalendarClient."""
        return self.calendar.cleanup_events

    @cleanup_old_events.setter
    def cleanup_old_events(self, func):
        self.calendar.cleanup_events = func

    def send_telegram_alert(self, message):
        """Dispatches operational alert via notifier module."""
        return send_telegram_alert(message, session=self.session)


def main(argv=None):
    """
    Main CLI entry point for local execution and GitHub Actions runners.
    """
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(
        description="Edus School to Google Calendar Synchronization Tool"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["schedule", "holidays"],
        help="Sync mode: 'schedule' (timetable and meals) or 'holidays' (vacations and exclude days)"
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of future weeks to synchronize for schedule (default: 1)"
    )
    args = parser.parse_args(argv)

    required_vars = [
        "SCHOOL_HOST",
        "SCHOOL_TOKEN",
        "SCHOOL_USER_UUID",
        "GOOGLE_CALENDAR_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON"
    ]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("💡 Create a .env.local file (based on .env.example) or configure repository secrets.")
        return 1

    try:
        credentials_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    except json.JSONDecodeError as e:
        print(f"❌ Invalid GOOGLE_SERVICE_ACCOUNT_JSON format: {e}")
        return 1

    sync = SchoolSync(
        host=os.environ["SCHOOL_HOST"],
        token=os.environ["SCHOOL_TOKEN"],
        user_uuid=os.environ["SCHOOL_USER_UUID"],
        calendar_id=os.environ["GOOGLE_CALENDAR_ID"],
        credentials_info=credentials_info
    )

    if args.mode == "schedule":
        sync.sync_schedule_flow(weeks_ahead=args.weeks)
    else:
        sync.sync_holidays()

    return 0


if __name__ == "__main__":
    sys.exit(main())
