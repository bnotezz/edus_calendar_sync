"""
Orchestrator service for synchronizing Edus.school data with Google Calendar.

Coordinates the end-to-end synchronization workflow:
- Step 1: Query Edus API for weekly schedule, canteen meals, and school calendar
- Step 2: Transform raw payloads into validated Google Calendar event representations
- Step 3: Upsert events into Google Calendar with rate-limiting and backoff protection
- Step 4: Reconcile and clean up canceled or shifted timeslots
"""

import logging
from datetime import datetime, timedelta

from calendar_mapper import (
    map_schedule_item_to_event,
    map_holiday_to_event
)

logger = logging.getLogger(__name__)


class SyncService:
    """Coordinates domain data extraction, transformation, and calendar upsertion."""

    def __init__(self, edus_client, calendar_client, user_uuid, today=None, load_location=True):
        """
        Initialize the synchronization coordinator.

        :param edus_client: Configured EdusClient instance
        :param calendar_client: Configured GoogleCalendarClient instance
        :param user_uuid: Target student's UUID in Edus
        :param today: Optional datetime.date override (defaults to current date)
        :param load_location: Whether to auto-query and attach school location
        """
        self.edus = edus_client
        self.calendar = calendar_client
        self.user_uuid = user_uuid
        self.today = today or datetime.now().date()
        self.school_location = self.edus.get_school_location() if load_location else None

    # =========================================================================
    # Schedule Synchronization Flow
    # =========================================================================

    def sync_schedule(self, weeks_ahead=1):
        """
        Executes the full schedule synchronization pipeline:
        1. Calculates weekly windows (current week + upcoming weeks)
        2. Retrieves canteen menu mappings
        3. Retrieves and transforms schedule records
        4. Upserts all future events into Google Calendar
        5. Purges cancelled or shifted timeslots

        :param weeks_ahead: Number of additional future weeks to sync (default 1)
        :return: Summary dictionary {"total_saved": int, "deleted_count": int, "active_count": int}
        """
        print("📚 Початок синхронізації розкладу...")
        current_monday = self.today - timedelta(days=self.today.weekday())
        weeks = [current_monday + timedelta(days=7 * i) for i in range(weeks_ahead + 1)]
        end_of_period = weeks[-1] + timedelta(days=7)

        # 1. Fetch canteen menu
        menu_data = self.edus.get_canteen_menu()
        menu_map = {m['week_day']: m['dishes'] for m in menu_data.get('menu', []) if 'week_day' in m}

        total_saved = 0
        active_event_ids = set()

        # 2. Iterate weeks and process schedule items
        for monday in weeks:
            start_date_str = monday.strftime('%Y-%m-%d')
            schedule_data = self.edus.get_schedule(self.user_uuid, start_date=start_date_str)

            for item in schedule_data.get('schedule', []):
                event_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
                if event_date < self.today:
                    continue  # Skip historical dates

                # Transform domain item into calendar event specification
                event_spec = map_schedule_item_to_event(
                    item=item,
                    menu_map=menu_map,
                    school_location=self.school_location
                )

                active_event_ids.add(event_spec["eid"])

                # Upsert into Google Calendar
                self.calendar.upsert_event(
                    event_spec["eid"],
                    event_spec["summary"],
                    event_spec["desc"],
                    event_spec["start"],
                    event_spec["end"],
                    is_all_day=event_spec["is_all_day"],
                    transparency=event_spec["transparency"],
                    location=event_spec["location"],
                    color_id=event_spec["color_id"],
                    extended_properties=event_spec["extended_properties"]
                )
                total_saved += 1

        # 3. Clean up cancelled or modified past/future slots
        print("🧹 Очищення неактуальних та старих подій (у т.ч. старих дублікатів)...")
        deleted_count = self.calendar.cleanup_events(
            start_date=current_monday,
            end_date=end_of_period,
            active_ids=active_event_ids,
            prefix="sch"
        )

        print(f"✅ Синхронізація розкладу завершена. Збережено: {total_saved}, Видалено: {deleted_count}")
        return {
            "total_saved": total_saved,
            "deleted_count": deleted_count,
            "active_count": len(active_event_ids)
        }

    # =========================================================================
    # Holidays Synchronization Flow
    # =========================================================================

    def sync_holidays(self):
        """
        Executes the holiday synchronization pipeline:
        1. Retrieves exclude days and academic semesters from Edus
        2. Synthesizes summer vacation from semester 2 end date
        3. Upserts all future holidays as transparent all-day calendar events

        :return: Summary dictionary {"total_saved": int}
        """
        print("🏖️ Синхронізація канікул...")
        exclude_data = self.edus.get_exclude_days()
        semesters = self.edus.get_semesters()
        holidays = list(exclude_data.get("1", []))

        # Add summer vacation based on 2nd semester end date
        sem2 = next((s for s in semesters if s.get('name') == '2'), None)
        if sem2 and 'end_date' in sem2:
            holidays.append({
                "id": f"summer{sem2['id']}",
                "name": "Літні",
                "start_day": sem2['end_date'],
                "end_day": f"{sem2['end_date'][:4]}-08-31"
            })

        total_saved = 0
        for h in holidays:
            end_dt_obj = datetime.strptime(h['end_day'], '%Y-%m-%d').date()
            if end_dt_obj < self.today:
                continue  # Skip past holidays

            event_spec = map_holiday_to_event(h)
            self.calendar.upsert_event(
                event_spec["eid"],
                event_spec["summary"],
                event_spec["desc"],
                event_spec["start"],
                event_spec["end"],
                is_all_day=event_spec["is_all_day"],
                transparency=event_spec["transparency"]
            )
            total_saved += 1

        print(f"✅ Синхронізація канікул завершена. Всього збережено подій: {total_saved}")
        return {"total_saved": total_saved}
