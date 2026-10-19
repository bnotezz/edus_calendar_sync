import unittest
from calendar_mapper import (
    get_subject_emoji,
    get_lesson_color_id,
    build_schedule_event_id,
    build_holiday_event_id,
    map_schedule_item_to_event,
    map_holiday_to_event
)


class TestCalendarMapper(unittest.TestCase):
    def test_get_subject_emoji(self):
        self.assertEqual(get_subject_emoji("Математика"), "🧮")
        self.assertEqual(get_subject_emoji("Українська мова"), "🇺🇦")
        self.assertEqual(get_subject_emoji("Невідомий предмет", obj_type="lesson"), "📚")
        self.assertEqual(get_subject_emoji("Шкільна лінійка", obj_type="event"), "🔔")
        self.assertEqual(get_subject_emoji("Щось інше", obj_type="custom"), "📝")

    def test_get_lesson_color_id(self):
        # Google Calendar supports 1-11
        self.assertEqual(get_lesson_color_id(10), str((10 % 11) + 1))
        self.assertEqual(get_lesson_color_id("22"), str((22 % 11) + 1))
        self.assertIsNone(get_lesson_color_id(None))
        self.assertIsNone(get_lesson_color_id("not_a_number"))

    def test_build_schedule_event_id(self):
        eid_order = build_schedule_event_id("2026-10-20", order_num=3)
        self.assertEqual(eid_order, "sch20261020n3")

        eid_time = build_schedule_event_id("2026-10-20", order_num=None, start_time="14:30")
        self.assertEqual(eid_time, "sch20261020t1430")

    def test_build_holiday_event_id(self):
        self.assertEqual(build_holiday_event_id("autumn-1"), "holautumn1")
        self.assertEqual(build_holiday_event_id("winter_break_2"), "holwinterbreak2")

    def test_map_schedule_item_to_event_lesson(self):
        item = {
            "date": "2026-10-20",
            "week_day": 2,
            "order_num": 1,
            "start_time": "09:00",
            "end_time": "09:45",
            "schedule_object": {"id": 105, "type": "lesson", "name": "Математика"},
            "user": {"username": "Олена Петрівна"}
        }
        res = map_schedule_item_to_event(item, school_location="Ліцей Вільні")
        self.assertEqual(res["eid"], "sch20261020n1")
        self.assertIn("🧮 Математика", res["summary"])
        self.assertEqual(res["desc"], "Вчитель: Олена Петрівна")
        self.assertEqual(res["start"], "2026-10-20T09:00:00")
        self.assertEqual(res["end"], "2026-10-20T09:45:00")
        self.assertEqual(res["location"], "Ліцей Вільні")
        self.assertEqual(res["color_id"], str((105 % 11) + 1))
        self.assertEqual(res["extended_properties"]["private"]["edus_object_id"], "105")

    def test_map_schedule_item_to_event_menu_match(self):
        item = {
            "date": "2026-10-21",
            "week_day": 3,
            "order_num": None,
            "start_time": "13:00",
            "end_time": "13:30",
            "schedule_object": {"id": 202, "type": "event", "name": "Обід"},
            "user": {}
        }
        menu_map = {
            3: [
                {"event_name": "Сніданок", "dish": "Млинці"},
                {"event_name": "Обід", "dish": "Суп гороховий, гречка з котлетою"}
            ]
        }
        res = map_schedule_item_to_event(item, menu_map=menu_map)
        self.assertEqual(res["eid"], "sch20261021t1300")
        self.assertIn("🍲 Обід", res["summary"])
        self.assertEqual(res["desc"], "Суп гороховий, гречка з котлетою")
        self.assertIsNone(res["color_id"])

    def test_map_holiday_to_event(self):
        holiday = {
            "id": "autumn-2026",
            "name": "Осінні",
            "start_day": "2026-10-26",
            "end_day": "2026-11-01"
        }
        res = map_holiday_to_event(holiday)
        self.assertEqual(res["eid"], "holautumn2026")
        self.assertEqual(res["summary"], "🏖️ Осінні канікули")
        self.assertEqual(res["start"], "2026-10-26")
        # Exclusive Google Calendar end date: 2026-11-01 + 1 day = 2026-11-02
        self.assertEqual(res["end"], "2026-11-02")
        self.assertTrue(res["is_all_day"])
        self.assertEqual(res["transparency"], "transparent")


if __name__ == "__main__":
    unittest.main()
