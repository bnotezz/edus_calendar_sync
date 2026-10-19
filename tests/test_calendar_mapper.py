import unittest
from calendar_mapper import (
    get_subject_emoji,
    get_lesson_color_id,
    build_schedule_event_id,
    build_holiday_event_id,
    build_lesson_planning_index,
    build_homework_index,
    format_event_description,
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

    def test_build_lesson_planning_index(self):
        plannings = {
            2589: {
                "id": 2589,
                "lesson": {"id": 17, "name": "Інформатика"},
                "themes": [
                    {
                        "id": 195322,
                        "name": "Досліджуємо GPS навігатор",
                        "content": "Робота з Google Maps",
                        "date": "2026-10-20",
                        "order_num": 8,
                        "is_materials": True
                    }
                ]
            }
        }
        index = build_lesson_planning_index(plannings)
        self.assertIn(("2026-10-20", "17"), index)
        self.assertIn(("2026-10-20", "інформатика"), index)
        info = index[("2026-10-20", "17")]
        self.assertEqual(info["theme_id"], 195322)
        self.assertEqual(info["theme_name"], "Досліджуємо GPS навігатор")
        self.assertEqual(info["theme_content"], "Робота з Google Maps")
        self.assertTrue(info["is_materials"])

    def test_build_homework_index(self):
        # 1792443600.0 corresponds to 2026-10-20 00:00:00 UTC+3
        homework_data = {
            "next": [
                {
                    "lesson": {"id": 1, "name": "Українська мова"},
                    "theme": {
                        "id": 199893,
                        "name": "Житомир. Комахи",
                        "content": "Робота за віршем Муха"
                    },
                    "homework_tasks": [
                        {"title": "Вивчити вірш до п'ятниці", "is_files": True}
                    ],
                    "prepare_till": "20 жовтня",
                    "lesson_timestamp": 1792443600.0,
                    "is_completed": False,
                    "class_group_id": 2087
                }
            ],
            "previous": []
        }
        hw_by_key, all_hw_by_date = build_homework_index(homework_data)
        self.assertIn(("2026-10-20", "1"), hw_by_key)
        self.assertIn(("2026-10-20", "українська мова"), hw_by_key)
        self.assertIn("2026-10-20", all_hw_by_date)

        hw = hw_by_key[("2026-10-20", "1")]
        self.assertEqual(hw["theme_name"], "Житомир. Комахи")
        self.assertEqual(hw["tasks"], ["Вивчити вірш до п'ятниці"])
        self.assertTrue(hw["has_files"])
        self.assertEqual(hw["prepare_till"], "20 жовтня")

    def test_format_event_description(self):
        # 1. Only teacher
        d1 = format_event_description(teacher="Олена Коваль")
        self.assertEqual(d1, "Вчитель: Олена Коваль")

        # 2. Teacher + theme + description
        d2 = format_event_description(
            teacher="Олена Коваль",
            theme_name="Ділення з остачею",
            theme_content="Пояснення правила"
        )
        self.assertIn("👨‍🏫 Вчитель: Олена Коваль", d2)
        self.assertIn("📖 ТЕМА УРОКУ:\nДілення з остачею", d2)
        self.assertIn("📝 ПРО УРОК:\nПояснення правила", d2)

        # 3. Homework with tasks and files
        hw = {
            "tasks": ["Номер 123", "Номер 124"],
            "prepare_till": "21 жовтня",
            "is_completed": False
        }
        d3 = format_event_description(
            teacher="Олена Коваль",
            theme_name="Ділення",
            homework=hw,
            material_files=["https://cdn.example.com/file1.jpg"]
        )
        self.assertIn("📌 ДОМАШНЄ ЗАВДАННЯ (до 21 жовтня):", d3)
        self.assertIn("• Номер 123", d3)
        self.assertIn("📎 МАТЕРІАЛИ ТА ФАЙЛИ:\n• https://cdn.example.com/file1.jpg", d3)

    def test_map_schedule_item_to_event_with_planning_and_homework(self):
        item = {
            "date": "2026-10-20",
            "week_day": 2,
            "order_num": 1,
            "start_time": "09:00",
            "end_time": "09:45",
            "schedule_object": {"id": 17, "type": "lesson", "name": "Інформатика"},
            "user": {"username": "Наталя Бучинська"}
        }
        planning_index = {
            ("2026-10-20", "17"): {
                "theme_id": 195322,
                "theme_name": "Google Maps",
                "theme_content": "Практика навігації",
                "order_num": 8
            }
        }
        # 1. With planning only (no homework yet)
        res_plan = map_schedule_item_to_event(item, planning_index=planning_index)
        self.assertEqual(res_plan["summary"], "💻 Інформатика")
        self.assertIn("📖 ТЕМА УРОКУ:\nGoogle Maps", res_plan["desc"])
        self.assertIn("📝 ПРО УРОК:\nПрактика навігації", res_plan["desc"])
        self.assertEqual(res_plan["extended_properties"]["private"]["has_homework"], "false")

        # 2. With homework added later
        homework_index = {
            ("2026-10-20", "17"): {
                "theme_id": 195322,
                "theme_name": "Google Maps",
                "theme_content": "Практика навігації",
                "tasks": ["Скласти маршрут від школи до дому"],
                "prepare_till": "21 жовтня",
                "is_completed": True
            }
        }
        res_hw = map_schedule_item_to_event(
            item,
            planning_index=planning_index,
            homework_index=homework_index
        )
        self.assertEqual(res_hw["summary"], "💻 Інформатика 📝")
        self.assertIn("📌 ДОМАШНЄ ЗАВДАННЯ (до 21 жовтня):", res_hw["desc"])
        self.assertIn("• Скласти маршрут від школи до дому", res_hw["desc"])
        self.assertEqual(res_hw["extended_properties"]["private"]["has_homework"], "true")

    def test_map_schedule_item_to_event_samopidgotovka(self):
        item = {
            "date": "2026-10-20",
            "week_day": 2,
            "order_num": 7,
            "start_time": "15:00",
            "end_time": "16:00",
            "schedule_object": {"id": 999, "type": "lesson", "name": "Самопідготовка"},
            "user": {}
        }
        all_day_hw = {
            "2026-10-20": [
                {
                    "lesson_name": "Математика",
                    "tasks": ["Вправа 45"],
                    "prepare_till": "21 жовтня",
                    "is_completed": False
                },
                {
                    "lesson_name": "Українська мова",
                    "tasks": ["Словниковий диктант"],
                    "prepare_till": "21 жовтня",
                    "is_completed": True
                }
            ]
        }
        res = map_schedule_item_to_event(item, all_day_homework=all_day_hw)
        self.assertEqual(res["summary"], "✏️ Самопідготовка")
        self.assertIn("✏️ САМОПІДГОТОВКА (План завдань):", res["desc"])
        self.assertIn("1. Математика (до 21 жовтня):", res["desc"])
        self.assertIn("   • Вправа 45", res["desc"])
        self.assertIn("2. Українська мова (до 21 жовтня):", res["desc"])
        self.assertIn("   • Словниковий диктант", res["desc"])


if __name__ == "__main__":
    unittest.main()
