import os
import requests
import argparse
import json
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

class SchoolSync:
    def __init__(self, host, token, calendar_id, user_uuid, credentials_info):
        self.host = host.rstrip('/')
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.calendar_id = calendar_id
        self.user_uuid = user_uuid
        creds = service_account.Credentials.from_service_account_info(credentials_info)
        self.service = build('calendar', 'v3', credentials=creds)
        self.today = datetime.now().date()

    def send_telegram_alert(self, message):
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            try:
                requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
            except: pass

    def fetch_data(self, path, params=None):
        response = requests.get(f"{self.host}/api/{path}", headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        count = 0
        if 'schedule' in data: count = len(data['schedule'])
        elif 'menu' in data: count = len(data['menu'])
        elif '1' in data: count = len(data['1'])
        print(f"📡 Отримано дані з {path}. Знайдено записів: {count}")
        return data

    def sync_holidays(self):
        print("🏖️ Синхронізація канікул...")
        exclude_data = self.fetch_data("school/exclude-day/")
        semesters = self.fetch_data("school/year/semester/")
        holidays = exclude_data.get("1", [])
        
        sem2 = next((s for s in semesters if s['type'] == 'two' and s['name'] == '2'), None)
        if sem2:
            holidays.append({
                "id": f"summer{sem2['id']}",
                "name": "Літні",
                "start_day": sem2['end_date'],
                "end_day": f"{sem2['end_date'][:4]}-08-31"
            })

        for h in holidays:
            end_dt_obj = datetime.strptime(h['end_day'], '%Y-%m-%d').date()
            if end_dt_obj < self.today: continue

            gcal_end = (end_dt_obj + timedelta(days=1)).strftime('%Y-%m-%d')
            name = h['name'] if "канікули" in h['name'].lower() else f"{h['name']} канікули"
            
            self.upsert_event(f"hol{h['id']}".replace("-", ""), f"🏖️ {name}", "Відпочинок", 
                             h['start_day'], gcal_end, is_all_day=True, transparency='transparent')

    def sync_schedule_flow(self):
        print("📚 Початок синхронізації розкладу...")
        current_monday = self.today - timedelta(days=self.today.weekday())
        next_monday = current_monday + timedelta(days=7)
        
        menu_data = self.fetch_data("kitchen/menu/")
        menu_map = {m['week_day']: m['dishes'] for m in menu_data.get('menu', [])}

        weeks = [current_monday, next_monday]
        total_saved = 0

        for monday in weeks:
            start_date_str = monday.strftime('%Y-%m-%d')
            schedule_data = self.fetch_data(f"schedule/for-user/{self.user_uuid}/", 
                                          params={"start_date": start_date_str})
            
            for item in schedule_data.get('schedule', []):
                event_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
                if event_date < self.today: continue

                obj = item.get('schedule_object', {})
                name = obj.get('name', 'Без назви')
                obj_type = obj.get('type')
                
                user_info = item.get('user') or {}
                teacher = user_info.get('username', 'Не вказано')
                desc = f"Вчитель: {teacher}"
                
                # Логіка для харчування
                if name in ["Сніданок", "Обід", "Вечеря"]:
                    day_menu = menu_map.get(item['week_day'], [])
                    dish = next((d for d in day_menu if d['event_name'] == name), None)
                    summary = f"🍽️ {name}" # Назва без меню
                    desc = dish['dish'] if dish else "" # Тільки текст меню в описі
                # Логіка для інших типів подій
                elif obj_type == 'lesson':
                    summary = f"📚 {name}"
                elif obj_type == 'event':
                    summary = f"🔔 {name}"
                else:
                    summary = f"📝 {name}"

                self.upsert_event(f"sch{item['id']}", summary, desc, 
                                 f"{item['date']}T{item['start_time']}:00", 
                                 f"{item['date']}T{item['end_time']}:00",
                                 transparency='opaque')
                total_saved += 1

        print(f"✅ Синхронізація завершена. Всього збережено/оновлено подій: {total_saved}")

    def upsert_event(self, eid, summary, desc, start, end, is_all_day=False, transparency='opaque'):
        t_key = 'date' if is_all_day else 'dateTime'
        body = {
            'id': eid, 'summary': summary, 'description': desc,
            'start': {t_key: start, 'timeZone': 'Europe/Kyiv'},
            'end': {t_key: end, 'timeZone': 'Europe/Kyiv'},
            'transparency': transparency
        }
        try:
            self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        except:
            self.service.events().update(calendarId=self.calendar_id, eventId=eid, body=body).execute()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()

    sync = SchoolSync(
        host=os.environ["SCHOOL_HOST"],
        token=os.environ["SCHOOL_TOKEN"],
        user_uuid=os.environ["SCHOOL_USER_UUID"],
        calendar_id=os.environ["GOOGLE_CALENDAR_ID"],
        credentials_info=json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    )

    if args.mode == "schedule": sync.sync_schedule_flow()
    else: sync.sync_holidays()