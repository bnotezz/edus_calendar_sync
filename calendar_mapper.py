"""
Mappers and formatters for transforming Edus.school data into Google Calendar events.

Contains:
- Emoji mappings for school subjects
- Stable Timeslot ID generation
- Subject color calculation
- Mapping of schedule and holiday items to calendar event specifications
"""

from datetime import datetime, timedelta, timezone

SUBJECT_EMOJIS = {
    "Математика": "🧮",
    "Українська мова": "🇺🇦",
    "Англійська мова": "🇬🇧",
    "Я досліджую світ": "🌍",
    "Інформатика": "💻",
    "Мистецтво": "🎨",
    "Дизайн": "🎨",
    "Фізкультура": "⚽",
    "Плавання": "🏊",
    "Музика": "🎵",
    "Театр": "🎭",
    "Велоспорт": "🚴",
    "Мислення": "🧠",
    "Урок щастя": "😊",
    "Science": "🔬",
    "Ранкова зустріч": "🌅",
    "Читання": "📖",
    "Сніданок": "🍳",
    "Обід": "🍲",
    "Вечеря": "🍽️",
    "Прогулянка": "🚶",
    "Самопідготовка": "✏️",
    "Вечірні теревені": "💬"
}


def get_subject_emoji(name, obj_type=None):
    """
    Returns an appropriate emoji for a subject or event name.

    :param name: Subject or event title
    :param obj_type: Object type ('lesson', 'event', etc.)
    :return: Emoji string
    """
    if name in SUBJECT_EMOJIS:
        return SUBJECT_EMOJIS[name]
    if obj_type == 'lesson':
        return "📚"
    if obj_type == 'event':
        return "🔔"
    return "📝"


def get_lesson_color_id(obj_id):
    """
    Derives a stable Google Calendar color ID (1-11) based on lesson object ID.

    :param obj_id: Unique object identifier from Edus
    :return: Color ID string or None
    """
    if not obj_id:
        return None
    try:
        return str((int(obj_id) % 11) + 1)
    except (ValueError, TypeError):
        return None


def build_schedule_event_id(date_str, order_num=None, start_time=None):
    """
    Builds a deterministic, unique Google Calendar event ID for a schedule slot.

    :param date_str: Date string 'YYYY-MM-DD'
    :param order_num: Lesson order number (e.g., 1, 2, 3)
    :param start_time: Start time 'HH:MM' if order_num is not available
    :return: Sanitized string ID (e.g., 'sch20261020n1' or 'sch20261020t0900')
    """
    date_clean = date_str.replace('-', '')
    if order_num is not None:
        return f"sch{date_clean}n{order_num}"
    clean_time = (start_time or '00:00').replace(':', '')
    return f"sch{date_clean}t{clean_time}"


def build_holiday_event_id(holiday_id):
    """
    Builds a sanitized holiday event ID.

    :param holiday_id: Raw holiday ID from Edus API
    :return: Sanitized string ID (e.g., 'holautumn1')
    """
    clean_id = str(holiday_id).replace('-', '').replace('_', '')
    return f"hol{clean_id}"


def build_lesson_planning_index(plannings):
    """
    Indexes curriculum planning themes by (date, lesson_id) and (date, lesson_name).

    :param plannings: Dict or list of planning objects from teacher/lesson-planning/
    :return: Dict mapping (date, lesson_id/name) to theme details
    """
    index = {}
    if not plannings:
        return index

    planning_list = plannings.values() if isinstance(plannings, dict) else plannings
    for plan in planning_list:
        if not isinstance(plan, dict):
            continue
        lesson = plan.get("lesson") or {}
        lesson_id = str(lesson.get("id")) if lesson.get("id") is not None else None
        lesson_name = lesson.get("name", "").strip().lower()

        for theme in plan.get("themes", []):
            if not isinstance(theme, dict):
                continue
            theme_date = theme.get("date")
            if not theme_date:
                continue

            theme_info = {
                "theme_id": theme.get("id"),
                "theme_name": (theme.get("name") or "").strip(),
                "theme_content": (theme.get("content") or theme.get("content_html") or "").strip(),
                "order_num": theme.get("order_num"),
                "is_materials": theme.get("is_materials", False)
            }
            if lesson_id:
                index[(theme_date, lesson_id)] = theme_info
            if lesson_name:
                index[(theme_date, lesson_name)] = theme_info
    return index


def build_homework_index(homework_data, timezone_offset_hours=3):
    """
    Indexes active homework assignments by (date, lesson_id) and (date, lesson_name).
    Also produces an all_hw_by_date index for daily checklists (e.g., Самопідготовка).

    :param homework_data: Payload from student/homework-tasks/{uuid}/active/
    :param timezone_offset_hours: UTC offset in hours if ZoneInfo unavailable
    :return: Tuple of (hw_by_key, all_hw_by_date)
    """
    hw_by_key = {}
    all_hw_by_date = {}
    if not isinstance(homework_data, dict):
        return hw_by_key, all_hw_by_date

    try:
        from zoneinfo import ZoneInfo
        kyiv_tz = ZoneInfo("Europe/Kyiv")
    except Exception:
        kyiv_tz = timezone(timedelta(hours=timezone_offset_hours))

    items = homework_data.get("next", []) + homework_data.get("previous", [])
    for item in items:
        if not isinstance(item, dict):
            continue
        lesson = item.get("lesson") or {}
        lesson_id = str(lesson.get("id")) if lesson.get("id") is not None else None
        lesson_name = lesson.get("name", "").strip().lower()

        theme = item.get("theme") or {}
        theme_id = theme.get("id")
        theme_name = (theme.get("name") or "").strip()
        theme_content = (theme.get("content") or theme.get("content_html") or "").strip()

        tasks = [t.get("title", "").strip() for t in item.get("homework_tasks", []) if isinstance(t, dict) and t.get("title")]
        prepare_till = item.get("prepare_till")
        is_completed = item.get("is_completed", False)
        class_group_id = item.get("class_group_id")
        has_files = any(t.get("is_files") for t in item.get("homework_tasks", []) if isinstance(t, dict))

        ts = item.get("lesson_timestamp")
        if not ts:
            continue
        try:
            date_str = datetime.fromtimestamp(float(ts), kyiv_tz).strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError):
            continue

        hw_entry = {
            "lesson_id": lesson_id,
            "lesson_name": lesson.get("name"),
            "theme_id": theme_id,
            "theme_name": theme_name,
            "theme_content": theme_content,
            "tasks": tasks,
            "prepare_till": prepare_till,
            "is_completed": is_completed,
            "has_files": has_files,
            "class_group_id": class_group_id
        }

        if lesson_id:
            hw_by_key[(date_str, lesson_id)] = hw_entry
        if lesson_name:
            hw_by_key[(date_str, lesson_name)] = hw_entry

        if date_str not in all_hw_by_date:
            all_hw_by_date[date_str] = []
        all_hw_by_date[date_str].append(hw_entry)

    return hw_by_key, all_hw_by_date


def format_event_description(teacher=None, theme_name=None, theme_content=None,
                             homework=None, menu_dish=None, all_day_homework=None,
                             material_files=None):
    """
    Constructs an event description incorporating teacher, curriculum theme,
    description, homework, or canteen meal information.
    """
    if menu_dish:
        return menu_dish

    if all_day_homework:
        lines = ["✏️ САМОПІДГОТОВКА (План завдань):"]
        for idx, hw in enumerate(all_day_homework, 1):
            name = hw.get("lesson_name") or "Урок"
            till = f" (до {hw['prepare_till']})" if hw.get("prepare_till") else ""
            lines.append(f"{idx}. {name}{till}:")
            for task in hw.get("tasks", []):
                lines.append(f"   • {task}")
        return "\n".join(lines)

    blocks = []
    if teacher:
        blocks.append(f"👨‍🏫 Вчитель: {teacher}")
    if theme_name:
        blocks.append(f"📖 ТЕМА УРОКУ:\n{theme_name}")
    if theme_content:
        blocks.append(f"📝 ПРО УРОК:\n{theme_content}")
    if homework and homework.get("tasks"):
        till = f" (до {homework['prepare_till']})" if homework.get("prepare_till") else ""
        tasks_text = "\n".join(f"• {t}" for t in homework["tasks"])
        blocks.append(f"📌 ДОМАШНЄ ЗАВДАННЯ{till}:\n{tasks_text}")
    if material_files:
        files_text = "\n".join(f"• {f}" for f in material_files)
        blocks.append(f"📎 МАТЕРІАЛИ ТА ФАЙЛИ:\n{files_text}")

    if not blocks:
        return ""
    # Maintain backward compatibility for items with only a teacher
    if len(blocks) == 1 and teacher and not theme_name and not theme_content and not (homework and homework.get("tasks")):
        return f"Вчитель: {teacher}"

    return "\n\n".join(blocks)


def map_schedule_item_to_event(item, menu_map=None, school_location=None,
                               planning_index=None, homework_index=None,
                               all_day_homework=None, materials_url_map=None):
    """
    Transforms a single Edus schedule item into Google Calendar event parameters.

    :param item: Dictionary representing a single schedule entry
    :param menu_map: Dictionary mapping week_day to list of dishes
    :param school_location: Location string (e.g., 'School Name, Address, City')
    :param planning_index: Optional dict mapping (date, lesson_id/name) to planned themes
    :param homework_index: Optional dict mapping (date, lesson_id/name) to active homework
    :param all_day_homework: Optional dict mapping date to list of all homework items
    :param materials_url_map: Optional dict mapping theme_id to list of file URLs
    :return: Dictionary with parameters ready for upsert_event
    """
    obj = item.get('schedule_object', {}) or {}
    name = obj.get('name', 'Без назви')
    obj_id = obj.get('id')
    obj_type = obj.get('type')
    user_info = item.get('user') or {}
    date_str = item.get('date', '')

    teacher = user_info.get('username')
    menu_dish = None

    # Match menu dish for breakfast, lunch, or dinner
    if name in ["Сніданок", "Обід", "Вечеря"] and menu_map:
        day_menu = menu_map.get(item.get('week_day'), [])
        dish = next((d for d in day_menu if d.get('event_name') == name), None)
        menu_dish = dish.get('dish', '') if dish else ""

    theme_info = None
    hw_info = None

    if planning_index:
        theme_info = planning_index.get((date_str, str(obj_id))) or planning_index.get((date_str, name.lower().strip()))
    if homework_index:
        hw_info = homework_index.get((date_str, str(obj_id))) or homework_index.get((date_str, name.lower().strip()))

    theme_name = (hw_info and hw_info.get("theme_name")) or (theme_info and theme_info.get("theme_name"))
    theme_content = (hw_info and hw_info.get("theme_content")) or (theme_info and theme_info.get("theme_content"))
    theme_id = (hw_info and hw_info.get("theme_id")) or (theme_info and theme_info.get("theme_id"))

    material_files = None
    if theme_id and materials_url_map:
        material_files = materials_url_map.get(theme_id)

    # Format description
    if name == "Самопідготовка" and all_day_homework and date_str in all_day_homework:
        desc = format_event_description(all_day_homework=all_day_homework[date_str])
    else:
        desc = format_event_description(
            teacher=teacher,
            theme_name=theme_name,
            theme_content=theme_content,
            homework=hw_info,
            menu_dish=menu_dish,
            material_files=material_files
        )

    emoji = get_subject_emoji(name, obj_type)
    has_hw = bool(hw_info and hw_info.get("tasks"))
    summary = f"{emoji} {name} 📝" if has_hw else f"{emoji} {name}"

    color_id = get_lesson_color_id(obj_id) if obj_type == 'lesson' else None

    extended_properties = {
        "private": {
            "edus_object_id": str(obj_id) if obj_id else "",
            "edus_object_type": obj_type or "",
            "edus_object_name": name,
            "edus_theme_id": str(theme_id) if theme_id else "",
            "has_homework": "true" if has_hw else "false"
        }
    }

    eid = build_schedule_event_id(
        date_str=item['date'],
        order_num=item.get('order_num'),
        start_time=item.get('start_time')
    )

    return {
        "eid": eid,
        "summary": summary,
        "desc": desc,
        "start": f"{item['date']}T{item['start_time']}:00",
        "end": f"{item['date']}T{item['end_time']}:00",
        "is_all_day": False,
        "transparency": "opaque",
        "location": school_location,
        "color_id": color_id,
        "extended_properties": extended_properties
    }


def map_holiday_to_event(holiday):
    """
    Transforms a holiday specification into Google Calendar event parameters.

    :param holiday: Dictionary containing 'id', 'name', 'start_day', 'end_day'
    :return: Dictionary with parameters ready for upsert_event
    """
    end_dt_obj = datetime.strptime(holiday['end_day'], '%Y-%m-%d').date()
    # Google Calendar all-day events have an exclusive end date (next day)
    gcal_end = (end_dt_obj + timedelta(days=1)).strftime('%Y-%m-%d')
    name = holiday['name'] if "канікули" in holiday['name'].lower() else f"{holiday['name']} канікули"
    eid = build_holiday_event_id(holiday['id'])

    return {
        "eid": eid,
        "summary": f"🏖️ {name}",
        "desc": "Відпочинок",
        "start": holiday['start_day'],
        "end": gcal_end,
        "is_all_day": True,
        "transparency": "transparent"
    }
