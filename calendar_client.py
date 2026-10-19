"""
Client for interacting with Google Calendar API v3.

Provides methods for:
- Initializing calendar connection using Google Cloud Service Account
- Safe event insertion/updating with exponential backoff for rate limits
- Listing events in specific time ranges
- Automated cleanup of outdated or canceled events
"""

import time
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleCalendarClient:
    """Client for performing CRUD operations on Google Calendar events."""

    def __init__(self, calendar_id, credentials_info=None, service=None, rate_limit_delay=0.5):
        """
        Initialize Google Calendar client.

        :param calendar_id: ID of the target Google Calendar (e.g., 'primary' or email)
        :param credentials_info: Service account credentials dictionary
        :param service: Pre-built googleapiclient service instance (optional, useful for testing)
        :param rate_limit_delay: Delay in seconds between API calls to avoid rate limits
        """
        self.calendar_id = calendar_id
        self.rate_limit_delay = rate_limit_delay

        if service:
            self.service = service
        elif credentials_info:
            creds = service_account.Credentials.from_service_account_info(credentials_info)
            self.service = build('calendar', 'v3', credentials=creds)
        else:
            raise ValueError("Either 'service' or 'credentials_info' must be provided.")

    def upsert_event(self, eid, summary, desc, start, end, is_all_day=False,
                     transparency='opaque', location=None, color_id=None,
                     extended_properties=None):
        """
        Inserts a new event or updates an existing one if a conflict (HTTP 409) occurs.
        Implements exponential backoff when encountering rate limits (HTTP 403 or 429).

        :param eid: Unique event identifier
        :param summary: Event title
        :param desc: Event description
        :param start: Start date/time ISO string
        :param end: End date/time ISO string
        :param is_all_day: If True, uses 'date' format instead of 'dateTime'
        :param transparency: 'opaque' (busy) or 'transparent' (free)
        :param location: Optional physical location string
        :param color_id: Optional Google Calendar color ID ('1' - '11')
        :param extended_properties: Optional metadata dictionary
        :return: Inserted or updated event dictionary
        """
        t_key = 'date' if is_all_day else 'dateTime'
        body = {
            'id': eid,
            'summary': summary,
            'description': desc,
            'start': {t_key: start, 'timeZone': 'Europe/Kyiv'},
            'end': {t_key: end, 'timeZone': 'Europe/Kyiv'},
            'transparency': transparency
        }
        if location:
            body['location'] = location
        if color_id:
            body['colorId'] = color_id
        if extended_properties:
            body['extendedProperties'] = extended_properties

        # Exponential Backoff Logic (5 attempts)
        for n in range(5):
            try:
                try:
                    result = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
                except HttpError as e:
                    if e.resp.status == 409:  # Conflict: event already exists
                        result = self.service.events().update(
                            calendarId=self.calendar_id, eventId=eid, body=body
                        ).execute()
                    else:
                        raise e

                if self.rate_limit_delay:
                    time.sleep(self.rate_limit_delay)
                return result
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    wait = (2 ** n) + 1
                    print(f"⏳ Перевищено ліміт Google API. Очікування {wait} сек...")
                    time.sleep(wait)
                else:
                    raise e

        raise RuntimeError(f"❌ Перевищено кількість спроб (5) для події {eid} через обмеження Google API")

    def delete_event(self, event_id):
        """
        Deletes a calendar event by its ID.

        :param event_id: ID of the event to delete
        :return: True if deleted successfully, False if not found or error
        """
        try:
            self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
            if self.rate_limit_delay:
                time.sleep(self.rate_limit_delay)
            return True
        except HttpError as e:
            print(f"⚠️ Помилка видалення події {event_id}: {e}")
            return False

    def list_events(self, time_min_rfc, time_max_rfc, max_results=2500, single_events=True):
        """
        Fetches events within a specific RFC3339 time window.

        :param time_min_rfc: Start boundary (e.g., '2026-10-20T00:00:00+03:00')
        :param time_max_rfc: End boundary (e.g., '2026-10-27T23:59:59+03:00')
        :param max_results: Maximum events to return per query
        :param single_events: Whether to expand recurring events
        :return: List of event dictionaries
        """
        events_result = self.service.events().list(
            calendarId=self.calendar_id,
            timeMin=time_min_rfc,
            timeMax=time_max_rfc,
            maxResults=max_results,
            singleEvents=single_events
        ).execute()
        return events_result.get('items', [])

    def cleanup_events(self, start_date, end_date, active_ids, prefix="sch", timezone_offset="+03:00"):
        """
        Removes outdated or cancelled events matching a prefix that are no longer active.

        :param start_date: datetime.date object representing start of period
        :param end_date: datetime.date object representing end of period
        :param active_ids: Set of event IDs that must be kept
        :param prefix: ID prefix to filter (defaults to 'sch' for school schedule)
        :param timezone_offset: Timezone offset string (defaults to '+03:00' for Kyiv)
        :return: Number of deleted events
        """
        start_rfc = f"{start_date.strftime('%Y-%m-%d')}T00:00:00{timezone_offset}"
        end_rfc = f"{end_date.strftime('%Y-%m-%d')}T23:59:59{timezone_offset}"

        try:
            events = self.list_events(start_rfc, end_rfc)
            deleted_count = 0
            for event in events:
                eid = event.get('id')
                if eid and eid.startswith(prefix) and eid not in active_ids:
                    if self.delete_event(eid):
                        deleted_count += 1

            if deleted_count > 0:
                print(f"🗑️ Видалено {deleted_count} старих дублікатів/скасованих подій.")
            else:
                print("✨ Немає подій для видалення, все актуально.")
            return deleted_count
        except Exception as e:
            print(f"⚠️ Не вдалося виконати очищення подій: {e}")
            return 0
