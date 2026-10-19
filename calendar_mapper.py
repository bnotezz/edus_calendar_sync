"""
Mappers and formatters for transforming Edus.school data into Google Calendar events.

Contains:
- Emoji mappings for school subjects
- Stable Timeslot ID generation
- Subject color calculation
- Mapping of schedule and holiday items to calendar event specifications
"""

from datetime import datetime, timedelta

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


def map_schedule_item_to_event(item, menu_map=None, school_location=None):
    """
    Transforms a single Edus schedule item into Google Calendar event parameters.

    :param item: Dictionary representing a single schedule entry
    :param menu_map: Dictionary mapping week_day to list of dishes
    :param school_location: Location string (e.g., 'School Name, Address, City')
    :return: Dictionary with parameters ready for upsert_event
    """
    obj = item.get('schedule_object', {}) or {}
    name = obj.get('name', 'Без назви')
    obj_id = obj.get('id')
    obj_type = obj.get('type')
    user_info = item.get('user') or {}

    emoji = get_subject_emoji(name, obj_type)
    summary = f"{emoji} {name}"

    teacher = user_info.get('username')
    desc = f"Вчитель: {teacher}" if teacher else ""

    # Match menu dish for breakfast, lunch, or dinner
    if name in ["Сніданок", "Обід", "Вечеря"] and menu_map:
        day_menu = menu_map.get(item.get('week_day'), [])
        dish = next((d for d in day_menu if d.get('event_name') == name), None)
        desc = dish.get('dish', '') if dish else ""

    color_id = get_lesson_color_id(obj_id) if obj_type == 'lesson' else None

    extended_properties = {
        "private": {
            "edus_object_id": str(obj_id) if obj_id else "",
            "edus_object_type": obj_type or "",
            "edus_object_name": name
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
