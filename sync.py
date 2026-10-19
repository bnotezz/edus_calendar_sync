import os
import requests
import argparse
import json
import time
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from edus_client import EdusClient

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
    def __init__(self, host, token, calendar_id, user_uuid, credentials_info=None,
                 service=None, session=None, rate_limit_delay=0.5, load_location=True,
                 edus_client=None):
        self.host = host.rstrip('/')
        self.calendar_id = calendar_id
        self.user_uuid = user_uuid
        self.rate_limit_delay = rate_limit_delay
        self.session = session or requests.Session()

        # Edus API Client component
        self.edus = edus_client or EdusClient(host=self.host, token=token, session=self.session)
        self.headers = self.edus.headers

        if service:
            self.service = service
        elif credentials_info:
            creds = service_account.Credentials.from_service_account_info(credentials_info)
            self.service = build('calendar', 'v3', credentials=creds)
        else:
            raise ValueError("Either 'service' or 'credentials_info' must be provided.")

        self.today = datetime.now().date()
        self.school_location = self.edus.get_school_location() if load_location else None

    def fetch_data(self, path, params=None, timeout=None):
        """Delegates data fetching to EdusClient for backwards compatibility."""
        return self.edus.fetch_data(path, params=params, timeout=timeout)

    def send_telegram_alert(self, message):
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            try:
                self.session.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
            except Exception as e:
                print(f"⚠️ Telegram alert failed: {e}")

    def get_school_location(self):
        """Fetches and formats school location via fetch_data."""
        try:
            general = self.fetch_data("school/settings/general/")
            contact = self.fetch_data("school/settings/contact/")
        except Exception as e:
            print(f"⚠️ Не вдалося отримати локацію школи: {e}")
            return None

        name = (general.get('name') or '').strip() if isinstance(general, dict) else ''
        address = (contact.get('address') or '').strip() if isinstance(contact, dict) else ''
        city = (contact.get('city') or '').strip() if isinstance(contact, dict) else ''

        parts = [part for part in [name, address, city] if part]
        if not parts:
            print("ℹ️ Локацію школи не знайдено в налаштуваннях")
            return None

        location = ", ".join(parts)
        print(f"📍 Локація для розкладу: {location}")
        return location

    def get_lessons_list(self):
        """Fetches lesson list via fetch_data."""
        print("⏳ Отримання списку уроків...")
        lesson_list = self.fetch_data(f"student/lesson-list/{self.user_uuid}/")
        print(f"✅ Отримано {len(lesson_list)} уроків.")
        return lesson_list

    def sync_holidays(self):
        print("🏖️ Синхронізація канікул...")
        exclude_data = self.fetch_data("school/exclude-day/")
        semesters = self.fetch_data("school/year/semester/")
        holidays = exclude_data.get("1", [])

        sem2 = next((s for s in semesters if s.get('name') == '2'), None)
        if sem2 and 'end_date' in sem2:
            holidays.append({
                "id": f"summer{sem2['id']}",
                "name": "Літні",
                "start_day": sem2['end_date'],
                "end_day": f"{sem2['end_date'][:4]}-08-31"
            })

        for h in holidays:
            end_dt_obj = datetime.strptime(h['end_day'], '%Y-%m-%d').date()
            if end_dt_obj < self.today:
                continue
            gcal_end = (end_dt_obj + timedelta(days=1)).strftime('%Y-%m-%d')
            name = h['name'] if "канікули" in h['name'].lower() else f"{h['name']} канікули"

            self.upsert_event(
                f"hol{h['id']}".replace("-", ""),
                f"🏖️ {name}",
                "Відпочинок",
                h['start_day'],
                gcal_end,
                is_all_day=True,
                transparency='transparent'
            )
            if self.rate_limit_delay:
                time.sleep(self.rate_limit_delay)

    def sync_schedule_flow(self):
        print("📚 Початок синхронізації розкладу...")
        current_monday = self.today - timedelta(days=self.today.weekday())
        next_monday = current_monday + timedelta(days=7)

        menu_data = self.fetch_data("kitchen/menu/")
        menu_map = {m['week_day']: m['dishes'] for m in menu_data.get('menu', []) if 'week_day' in m}

        weeks = [current_monday, next_monday]
        end_of_period = next_monday + timedelta(days=7)
        total_saved = 0
        active_event_ids = set()

        for monday in weeks:
            start_date_str = monday.strftime('%Y-%m-%d')
            schedule_data = self.fetch_data(
                f"schedule/for-user/{self.user_uuid}/",
                params={"start_date": start_date_str}
            )

            for item in schedule_data.get('schedule', []):
                event_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
                if event_date < self.today:
                    continue

                obj = item.get('schedule_object', {})
                name = obj.get('name', 'Без назви')
                obj_id = obj.get('id')
                obj_type = obj.get('type')
                user_info = item.get('user') or {}

                # 1. Емоджі та Назва
                emoji = SUBJECT_EMOJIS.get(name, "")
                if not emoji:
                    if obj_type == 'lesson':
                        emoji = "📚"
                    elif obj_type == 'event':
                        emoji = "🔔"
                    else:
                        emoji = "📝"

                summary = f"{emoji} {name}"

                teacher = user_info.get('username')
                desc = f"Вчитель: {teacher}" if teacher else ""

                if name in ["Сніданок", "Обід", "Вечеря"]:
                    day_menu = menu_map.get(item.get('week_day'), [])
                    dish = next((d for d in day_menu if d.get('event_name') == name), None)
                    desc = dish.get('dish', '') if dish else ""

                # 2. Колір (лише для уроків)
                color_id = None
                if obj_type == 'lesson' and obj_id:
                    color_id = str((int(obj_id) % 11) + 1)

                # 3. Приховані метадані (extendedProperties)
                extended_properties = {
                    "private": {
                        "edus_object_id": str(obj_id) if obj_id else "",
                        "edus_object_type": obj_type or "",
                        "edus_object_name": name
                    }
                }

                # Використовуємо комбінацію дати та номеру уроку як стабільний ID (timeslot)
                order = item.get('order_num')
                if order is not None:
                    eid = f"sch{item['date'].replace('-', '')}n{order}"
                else:
                    eid = f"sch{item['date'].replace('-', '')}t{item['start_time'].replace(':', '')}"

                active_event_ids.add(eid)

                self.upsert_event(
                    eid,
                    summary,
                    desc,
                    f"{item['date']}T{item['start_time']}:00",
                    f"{item['date']}T{item['end_time']}:00",
                    transparency='opaque',
                    location=self.school_location,
                    color_id=color_id,
                    extended_properties=extended_properties
                )
                total_saved += 1
                if self.rate_limit_delay:
                    time.sleep(self.rate_limit_delay)

        print("🧹 Очищення неактуальних та старих подій (у т.ч. старих дублікатів)...")
        self.cleanup_old_events(current_monday, end_of_period, active_event_ids)

        print(f"✅ Синхронізація завершена. Всього збережено/оновлено подій: {total_saved}")

    def cleanup_old_events(self, start_date, end_date, active_ids):
        start_rfc = f"{start_date.strftime('%Y-%m-%d')}T00:00:00+03:00"  # Часовий пояс Києва
        end_rfc = f"{end_date.strftime('%Y-%m-%d')}T23:59:59+03:00"

        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_rfc,
                timeMax=end_rfc,
                maxResults=2500,
                singleEvents=True
            ).execute()
            events = events_result.get('items', [])

            deleted_count = 0
            for event in events:
                eid = event.get('id')
                if eid and eid.startswith('sch') and eid not in active_ids:
                    try:
                        self.service.events().delete(calendarId=self.calendar_id, eventId=eid).execute()
                        deleted_count += 1
                        if self.rate_limit_delay:
                            time.sleep(self.rate_limit_delay)
                    except HttpError as e:
                        print(f"⚠️ Помилка видалення події {eid}: {e}")

            if deleted_count > 0:
                print(f"🗑️ Видалено {deleted_count} старих дублікатів/скасованих подій.")
            else:
                print("✨ Немає подій для видалення, все актуально.")

        except Exception as e:
            print(f"⚠️ Не вдалося виконати очищення подій: {e}")

    def upsert_event(self, eid, summary, desc, start, end, is_all_day=False,
                     transparency='opaque', location=None, color_id=None, extended_properties=None):
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

        # Exponential Backoff Logic
        for n in range(5):
            try:
                try:
                    self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
                except HttpError as e:
                    if e.resp.status == 409:
                        self.service.events().update(calendarId=self.calendar_id, eventId=eid, body=body).execute()
                    else:
                        raise e
                return
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    wait = (2 ** n) + 1
                    print(f"⏳ Перевищено ліміт Google API. Очікування {wait} сек...")
                    time.sleep(wait)
                else:
                    raise e
        raise RuntimeError(f"❌ Перевищено кількість спроб (5) для події {eid} через обмеження Google API")


def main(argv=None):
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description="Edus School to Google Calendar Sync")
    parser.add_argument("--mode", required=True, choices=["schedule", "holidays"], help="Sync mode")
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
        sync.sync_schedule_flow()
    else:
        sync.sync_holidays()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
