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
        # Поточна дата для фільтрації
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
        return response.json()

    def sync_holidays(self):
        print("🏖️ Синхронізація канікул...")
        exclude_data = self.fetch_data("school/exclude-day/")
        semesters = self.fetch_data("school/year/semester/")
        holidays = exclude_data.get("1", [])
        
        sem2 = next((s for s in semesters if s['type'] == 'two' and s['name'] == '2'), None)
        if sem2:
            holidays.append({
                "id": f"summer{sem2['id']}",
                "name": "Літні канікули",
                "start_day": sem2['end_date'],
                "end_day": f"{sem2['end_date'][:4]}-08-31"
            })

        for h in holidays:
            # Фільтрація: не зберігаємо канікули, що вже закінчилися
            end_date = datetime.strptime(h['end_day'], '%Y-%m-%d').date()
            if end_date < self.today:
                continue

            event_id = f"hol{h['id']}".replace("-", "")
            self.upsert_event(event_id, f"🏖️ {h['name']}", "Шкільні канікули", h['start_day'], h['end_day'], True)

    def sync_daily(self):
        print("📚 Початок синхронізації розкладу...")
        
        # Вираховуємо дати для запитів (поточний понеділок та наступний)
        current_monday = self.today - timedelta(days=self.today.weekday())
        next_monday = current_monday + timedelta(days=7)
        
        # Отримуємо меню один раз
        menu_data = self.fetch_data("kitchen/menu/")
        menu_map = {m['week_day']: m['dishes'] for m in menu_data.get('menu', [])}

        weeks_to_sync = [
            current_monday.strftime('%Y-%m-%d'),
            next_monday.strftime('%Y-%m-%d')
        ]

        total_synced = 0

        for week_date in weeks_to_sync:
            print(f"📡 Запит розкладу для тижня з {week_date}...")
            schedule_data = self.fetch_data(f"schedule/for-user/{self.user_uuid}/", params={"date": week_date})
            
            for item in schedule_data.get('schedule', []):
                event_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
                
                # 1. Фільтрація минулих подій: ігноруємо все, що було до сьогодні
                if event_date < self.today:
                    continue

                name = item['schedule_object']['name']
                desc = f"Вчитель: {item.get('user', {}).get('username', 'Не вказано')}"
                
                # 2. Збагачення меню (тільки для майбутніх подій їжі)
                if name in ["Сніданок", "Обід", "Вечеря"]:
                    day_menu = menu_map.get(item['week_day'], [])
                    dish = next((d for d in day_menu if d['event_name'] == name), None)
                    summary = f"🍽️ {name}: {dish['dish'].split(',')[0]}" if dish else f"🍽️ {name}"
                    desc = f"🥗 Повне меню: {dish['dish']}" if dish else ""
                else:
                    summary = f"📚 {name}"

                self.upsert_event(f"sch{item['id']}", summary, desc, 
                                 f"{item['date']}T{item['start_time']}:00", 
                                 f"{item['date']}T{item['end_time']}:00")
                total_synced += 1

        print(f"✅ Синхронізація завершена. Оброблено {total_synced} майбутніх подій.")

    def upsert_event(self, eid, summary, desc, start, end, is_all_day=False):
        t_key = 'date' if is_all_day else 'dateTime'
        body = {
            'id': eid, 'summary': summary, 'description': desc,
            'start': {t_key: start, 'timeZone': 'Europe/Kyiv'},
            'end': {t_key: end, 'timeZone': 'Europe/Kyiv'}
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

    try:
        if args.mode == "daily": sync.sync_daily()
        else: sync.sync_holidays()
    except Exception as e:
        sync.send_telegram_alert(f"🚨 Помилка School Sync: {e}")
        raise