import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock
from sync_service import SyncService


class TestSyncService(unittest.TestCase):
    def setUp(self):
        self.mock_edus = MagicMock()
        self.mock_calendar = MagicMock()
        self.today = date(2026, 10, 20)  # A Tuesday
        self.mock_edus.get_school_location.return_value = "Ліцей 'Вільні'"

        self.service = SyncService(
            edus_client=self.mock_edus,
            calendar_client=self.mock_calendar,
            user_uuid="student-uuid-123",
            today=self.today,
            load_location=True
        )

    def test_sync_schedule(self):
        # Setup mock menu
        self.mock_edus.get_canteen_menu.return_value = {
            "menu": [
                {"week_day": 2, "dishes": [{"event_name": "Обід", "dish": "Борщ"}]}
            ]
        }
        # Setup mock schedule
        future_date = (self.today + timedelta(days=1)).strftime("%Y-%m-%d")
        past_date = (self.today - timedelta(days=2)).strftime("%Y-%m-%d")

        self.mock_edus.get_schedule.return_value = {
            "schedule": [
                {
                    "date": future_date,
                    "week_day": 3,
                    "order_num": 1,
                    "start_time": "09:00",
                    "end_time": "09:45",
                    "schedule_object": {"id": 10, "type": "lesson", "name": "Математика"},
                    "user": {"username": "Вчитель"}
                },
                {
                    "date": past_date,
                    "week_day": 1,
                    "order_num": 1,
                    "start_time": "09:00",
                    "end_time": "09:45",
                    "schedule_object": {"id": 11, "type": "lesson", "name": "Фізика"},
                    "user": {}
                }
            ]
        }
        self.mock_calendar.cleanup_events.return_value = 2

        stats = self.service.sync_schedule(weeks_ahead=1)

        # 2 weeks queried, each week has 1 future event (past event skipped)
        self.assertEqual(stats["total_saved"], 2)
        self.assertEqual(stats["deleted_count"], 2)
        self.assertEqual(stats["active_count"], 1)
        self.assertEqual(self.mock_calendar.upsert_event.call_count, 2)
        self.mock_calendar.cleanup_events.assert_called_once()

    def test_sync_holidays(self):
        future_start = (self.today + timedelta(days=5)).strftime("%Y-%m-%d")
        future_end = (self.today + timedelta(days=12)).strftime("%Y-%m-%d")
        past_start = (self.today - timedelta(days=20)).strftime("%Y-%m-%d")
        past_end = (self.today - timedelta(days=15)).strftime("%Y-%m-%d")

        self.mock_edus.get_exclude_days.return_value = {
            "1": [
                {"id": "fall", "name": "Осінні", "start_day": future_start, "end_day": future_end},
                {"id": "past", "name": "Минулі", "start_day": past_start, "end_day": past_end}
            ]
        }
        self.mock_edus.get_semesters.return_value = [
            {"id": "1", "name": "1", "end_date": "2026-12-25"},
            {"id": "2", "name": "2", "end_date": "2027-06-01"}
        ]

        stats = self.service.sync_holidays()

        # 1 fall holiday + 1 summer vacation (past holiday skipped)
        self.assertEqual(stats["total_saved"], 2)
        self.assertEqual(self.mock_calendar.upsert_event.call_count, 2)

    def test_sync_schedule_with_planning_and_homework(self):
        tomorrow = (self.today + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_ts = datetime.combine(self.today + timedelta(days=1), datetime.min.time()).timestamp()

        self.mock_edus.get_canteen_menu.return_value = {"menu": []}
        self.mock_edus.get_lesson_list.return_value = [
            {
                "id": 102146,
                "lesson": {"id": 17, "name": "Інформатика"},
                "class_group": {"id": 2089},
                "lesson_plannings": [{"id": 2589}]
            }
        ]
        self.mock_edus.get_lesson_planning.return_value = {
            "id": 2589,
            "lesson": {"id": 17, "name": "Інформатика"},
            "themes": [
                {
                    "id": 195322,
                    "name": "Google Maps",
                    "content": "Робота з картами",
                    "date": tomorrow,
                    "order_num": 8
                }
            ]
        }
        self.mock_edus.get_active_homework.return_value = {
            "next": [
                {
                    "lesson": {"id": 17, "name": "Інформатика"},
                    "theme": {
                        "id": 195322,
                        "name": "Google Maps",
                        "content": "Робота з картами"
                    },
                    "homework_tasks": [
                        {"title": "Скласти маршрут", "is_files": True}
                    ],
                    "prepare_till": "21 жовтня",
                    "lesson_timestamp": tomorrow_ts,
                    "is_completed": False,
                    "class_group_id": 2089
                }
            ],
            "previous": []
        }
        self.mock_edus.get_theme_details.return_value = {
            "materials": [
                {"files": [{"file_url": "https://cdn.example.com/map_task.png"}]}
            ]
        }
        self.mock_edus.get_schedule.return_value = {
            "schedule": [
                {
                    "date": tomorrow,
                    "week_day": 2,
                    "order_num": 1,
                    "start_time": "10:00",
                    "end_time": "10:45",
                    "schedule_object": {"id": 17, "type": "lesson", "name": "Інформатика"},
                    "user": {"username": "Наталя Бучинська"}
                }
            ]
        }
        self.mock_calendar.cleanup_events.return_value = 0

        stats = self.service.sync_schedule(weeks_ahead=0)

        self.assertEqual(stats["total_saved"], 1)
        self.mock_calendar.upsert_event.assert_called_once()
        args, kwargs = self.mock_calendar.upsert_event.call_args
        # kwargs or args: (eid, summary, desc, start, end, ...)
        summary = kwargs.get("summary") or args[1]
        desc = kwargs.get("desc") or args[2]

        self.assertIn("💻 Інформатика 📝", summary)
        self.assertIn("📖 ТЕМА УРОКУ:\nGoogle Maps", desc)
        self.assertIn("📝 ПРО УРОК:\nРобота з картами", desc)
        self.assertIn("📌 ДОМАШНЄ ЗАВДАННЯ (до 21 жовтня):", desc)
        self.assertIn("• Скласти маршрут", desc)
        self.assertIn("📎 МАТЕРІАЛИ ТА ФАЙЛИ:\n• https://cdn.example.com/map_task.png", desc)


if __name__ == "__main__":
    unittest.main()
