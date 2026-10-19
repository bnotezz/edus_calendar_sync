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
    map_holiday_to_event,
    build_lesson_planning_index,
    build_homework_index
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
        3. Retrieves curriculum planning (КТП) and active homework assignments
        4. Retrieves and transforms schedule records enriched with themes & homework
        5. Upserts all future events into Google Calendar
        6. Purges cancelled or shifted timeslots

        :param weeks_ahead: Number of additional future weeks to sync (default 1)
        :return: Summary dictionary {"total_saved": int, "deleted_count": int, "active_count": int}
        """
        print("📚 Початок синхронізації розкладу...")
        current_monday = self.today - timedelta(days=self.today.weekday())
        weeks = [current_monday + timedelta(days=7 * i) for i in range(weeks_ahead + 1)]
        end_of_period = weeks[-1] + timedelta(days=7)

        # 1. Fetch canteen menu
        try:
            menu_data = self.edus.get_canteen_menu()
            menu_map = {m['week_day']: m['dishes'] for m in menu_data.get('menu', []) if 'week_day' in m}
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося завантажити меню: {e}")
            menu_map = {}

        # 2. Fetch curriculum planning (КТП) for student lessons
        plannings = {}
        try:
            lesson_list = self.edus.get_lesson_list(self.user_uuid)
            for lesson_entry in (lesson_list if isinstance(lesson_list, list) else []):
                if not isinstance(lesson_entry, dict):
                    continue
                plannings_list = lesson_entry.get("lesson_plannings") or []
                class_group = lesson_entry.get("class_group") or {}
                class_group_id = class_group.get("id") if isinstance(class_group, dict) else None
                for p in plannings_list:
                    if isinstance(p, dict) and p.get("id"):
                        p_id = p["id"]
                        if p_id not in plannings:
                            try:
                                plan_data = self.edus.get_lesson_planning(p_id, class_group_id=class_group_id)
                                if isinstance(plan_data, dict):
                                    plannings[p_id] = plan_data
                            except Exception as pe:
                                logger.warning(f"⚠️ Не вдалося завантажити КТП {p_id}: {pe}")
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося завантажити список уроків для КТП: {e}")
        planning_index = build_lesson_planning_index(plannings)

        # 3. Fetch active homework assignments
        homework_index = {}
        all_day_homework = {}
        materials_url_map = {}
        try:
            homework_data = self.edus.get_active_homework(self.user_uuid)
            homework_index, all_day_homework = build_homework_index(homework_data)

            # Точково дістаємо посилання на матеріали тільки якщо є файли
            for hw in homework_index.values():
                theme_id = hw.get("theme_id")
                if hw.get("has_files") and theme_id and theme_id not in materials_url_map:
                    try:
                        details = self.edus.get_theme_details(theme_id, class_group_id=hw.get("class_group_id"))
                        if isinstance(details, dict):
                            file_urls = []
                            for mat in details.get("materials", []):
                                for f in mat.get("files", []):
                                    url = f.get("file_url") or f.get("external_url")
                                    if url:
                                        file_urls.append(url)
                            if file_urls:
                                materials_url_map[theme_id] = file_urls
                    except Exception as fe:
                        logger.warning(f"⚠️ Не вдалося завантажити матеріали для теми {theme_id}: {fe}")
        except Exception as e:
            logger.warning(f"⚠️ Не вдалося завантажити активні ДЗ: {e}")

        total_saved = 0
        active_event_ids = set()

        # 4. Iterate weeks and process schedule items
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
                    school_location=self.school_location,
                    planning_index=planning_index,
                    homework_index=homework_index,
                    all_day_homework=all_day_homework,
                    materials_url_map=materials_url_map
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
