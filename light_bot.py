import telebot
from telebot import types
import subprocess
import json
import time
import threading
import os
import sys
import requests
from datetime import datetime

# --- [ РОБОТА З КОНФІГ-ФАЙЛОМ ] ---
try:
    from config import BOT_TOKEN, ADMIN_IDS, CHAT_ID
except ImportError:
    print("❌ Помилка: Файл config.py не знайдено! Запустіть Menu.sh для налаштування.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
last_power_state = None
REPO_URL = "https://github.com/Bombin1/PowerBot.git" 
MONO_URL = "https://send.monobank.ua/jar/8WFAPWLdPu"

SETTINGS_FILE = 'user_settings.json'
LOCAL_SCHEDULE_FILE = 'current_schedule.json'
VERSION = "2.8"  # Поточна версія бота
VERSION_URL = "https://raw.githubusercontent.com/Bombin1/PowerBot/main/version.txt"
CHANGELOG_URL = "https://raw.githubusercontent.com/Bombin1/PowerBot/main/changelog.txt"
last_update_check_day = None 
last_notified_version = None 

# --- [ СПИСОК МІСТ ТА ПОСИЛАНЬ ] ---
CITY_SOURCES = {
    "Київ": "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/kyiv.json",
    "Дніпро": "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/dnipro.json",
    "Одеса": "https://raw.githubusercontent.com/Baskerville42/outage-data-ua/main/data/odesa.json",
    "Вінниця": "https://raw.githubusercontent.com/olnet93/gpv-voe-vinnytsia/main/data/Vinnytsiaoblenerho.json",
    "Черкаси": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Cherkasyoblenergo.json",
    "Чернігів": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Chernihivoblenergo.json",
    "Харків": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Kharkivoblenerho.json",
    "Хмельницький": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Khmelnytskoblenerho.json",
    "Львів": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Lvivoblenerho.json",
    "Полтава": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Poltavaoblenergo.json",
    "Івано-Франківськ": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Prykarpattiaoblenerho.json",
    "Рівне": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Rivneoblenergo.json",
    "Тернопіль": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Ternopiloblenerho.json",
    "Ужгород": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Zakarpattiaoblenerho.json",
    "Запоріжжя": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Zaporizhzhiaoblenergo.json",
    "Житомир": "https://raw.githubusercontent.com/yaroslav2901/OE_OUTAGE_DATA/main/data/Zhytomyroblenergo.json"
}

# --- [ ЦЕНТРАЛІЗОВАНІ ТЕХНІЧНІ ПОВІДОМЛЕННЯ ] ---
def send_tech_info(text):
    """Надсилає технічну інформацію ТІЛЬКИ адмінам у приват"""
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            print(f"[LOG] Не вдалося надіслати в приват {admin_id}. Чат не розпочато.")

# --- [ РОБОТА З НАЛАШТУВАННЯМИ ] ---
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"notifications": False, "city": None, "queue": None, "last_hash": None}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- [ ПАРСИНГ ГРАФІКА ] ---
def format_schedule(data, queue_name):
    queue_data = None
    if 'fact' in data and 'data' in data['fact']:
        today_id = str(data['fact'].get('today', ''))
        fact_data = data['fact']['data']
        if today_id in fact_data:
            queue_data = fact_data[today_id].get(queue_name)
    if not queue_data:
        queue_data = data.get(queue_name)
    if not queue_data:
        return None

    time_zones = data.get("time_zone") or (data.get("preset") or {}).get("time_zone", {})
    time_types = data.get("time_type") or (data.get("preset") or {}).get("time_type", {})
    schedule_blocks = []
    current_status = None
    start_time = None
    
    for i in range(1, 25):
        key = str(i)
        status = queue_data.get(key)
        t_start, t_end = (time_zones[key][1], time_zones[key][2]) if time_zones and key in time_zones else (f"{i-1:02d}:00", f"{i:02d}:00")
        if status != current_status:
            if current_status is not None:
                schedule_blocks.append((current_status, start_time, t_start))
            current_status, start_time = status, t_start
        if i == 24:
            schedule_blocks.append((current_status, start_time, t_end))

    text = ""
    for status, s, e in schedule_blocks:
        if status == "no": icon, desc = "🔴", "Відключення"
        elif status == "yes": icon, desc = "🟢", "Світло Є"
        else:
            icon = "🟡"
            desc = time_types.get(status, "Можливе відключення")
        text += f"{icon} **{s} - {e}** — {desc}\n"
    return text

# --- [ ФОНОВІ ПРОЦЕСИ ] ---
def version_tuple(v):
    return tuple(map(int, v.strip().split(".")))

def check_updates_for_admin():
    global last_update_check_day, last_notified_version
    current_day = datetime.now().date()
    if last_update_check_day == current_day: return

    try:
        import random
        v_url = f"{VERSION_URL}?nocache={random.randint(1,1000)}"
        response = requests.get(v_url, timeout=15)
        if response.status_code != 200: return
        github_version = "".join(filter(lambda x: x.isdigit() or x == '.', response.text.strip()))
        
        if version_tuple(github_version) > version_tuple(VERSION):
            if last_notified_version == github_version: return
            changelog_text = "Опис змін доступний на GitHub."
            try:
                ch_resp = requests.get(CHANGELOG_URL, timeout=10)
                if ch_resp.status_code == 200: changelog_text = ch_resp.text.strip()
            except: pass

            msg = (
                f"🚀 **Доступне оновлення бота!**\n\n"
                f"Поточна версія: `{VERSION}`\n"
                f"Нова версія: `{github_version}`\n\n"
                f"📝 **Що нового:**\n{changelog_text}\n\n"
                f"Використайте `/set` у приваті для оновлення."
            )
            send_tech_info(msg) 
            last_notified_version = github_version
            last_update_check_day = current_day
    except Exception as e:
        print(f"[UPDATE ERROR] {e}")

def monitoring_loop():
    global last_power_state
    last_check_hour = -1
    last_schedule_text = "" 
    info = get_battery_info()
    if info: last_power_state = info["plugged"]
    
    while True:
        try:
            check_updates_for_admin()
            info = get_battery_info()
            if info and last_power_state is not None and info["plugged"] != last_power_state:
                text = "💡 **Світло з'явилось!**" if info["plugged"] else "🕯️ **Світло зникло!**"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                last_power_state = info["plugged"]
            
            now = datetime.now()
            settings = load_settings()
            if settings.get("notifications") and settings.get("city"):
                if now.hour != last_check_hour:
                    try:
                        r = requests.get(CITY_SOURCES[settings['city']], timeout=15)
                        if r.status_code == 200:
                            data = r.json()
                            current_schedule = format_schedule(data, settings['queue'])
                            if current_schedule and current_schedule != last_schedule_text:
                                q_num = settings['queue'].replace('GPV', '')
                                header_type = "📅 **Графік на сьогодні**" if not last_schedule_text or (0 <= now.hour < 4) else "⚠️ **Графік оновлено**"
                                bot.send_message(CHAT_ID, f"{header_type} ({q_num}):\n\n{current_schedule}", parse_mode="Markdown")
                                last_schedule_text = current_schedule
                                with open(LOCAL_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(data, f, ensure_ascii=False)
                            last_check_hour = now.hour
                    except Exception as e:
                        send_tech_info(f"🔴 **Помилка графіка:** {e}")
            time.sleep(30)
        except Exception as e:
            print(f"Помилка моніторингу: {e}")
            time.sleep(10)

# --- [ АДМІН-МЕНЮ ] ---
def get_update_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🤖 Бот", callback_data="upd_bot"),
               types.InlineKeyboardButton("🛫 Лаунчер", callback_data="upd_launcher"))
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_set"))
    return markup

def get_rollback_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🤖 Бот", callback_data="rb_bot"),
               types.InlineKeyboardButton("🛫 Лаунчер", callback_data="rb_launcher"))
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_set"))
    return markup

@bot.message_handler(func=lambda message: message.text in ["/set", "⚙️"])   
def admin_settings(message):
    # ПЕРЕВІРКА: Ігноруємо, якщо це не приватний чат або не адмін
    if message.chat.type != 'private' or message.from_user.id not in ADMIN_IDS:
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📊 Графік", callback_data="set_graph"))
    markup.add(types.InlineKeyboardButton("🔄 Оновлення", callback_data="exec_update"),
               types.InlineKeyboardButton("↩️ Відкат", callback_data="exec_rollback"))
    bot.send_message(message.chat.id, "🛠️ **Адмін-панель:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.message.chat.type != 'private': return
    settings = load_settings()

    if call.data == "set_graph":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Увімкнути", callback_data="notify_on"),
                   types.InlineKeyboardButton("❌ Вимкнути", callback_data="notify_off"))
        bot.edit_message_text("Дзвоник сповіщень про графік:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "exec_update":
        bot.edit_message_text("🔄 **Що саме оновити?**", call.message.chat.id, call.message.message_id, reply_markup=get_update_keyboard(), parse_mode="Markdown")

    elif call.data == "exec_rollback":
        bot.edit_message_text("↩️ **Що саме відкотити?**", call.message.chat.id, call.message.message_id, reply_markup=get_rollback_keyboard(), parse_mode="Markdown")

    elif call.data == "back_to_main_set":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📊 Графік", callback_data="set_graph"))
        markup.add(types.InlineKeyboardButton("🔄 Оновлення", callback_data="exec_update"),
                   types.InlineKeyboardButton("↩️ Відкат", callback_data="exec_rollback"))
        bot.edit_message_text("🛠️ **Адмін-панель:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "upd_bot":
        send_tech_info("🚀 **Оновлюю бота...**")
        os.system("cp light_bot.py light_bot.py.bak")
        os.system("git checkout origin/main -- light_bot.py")
        os._exit(0)

    elif call.data == "upd_launcher":
        bot.edit_message_text("🛫 **Оновлюю лаунчер...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        os.system("cp Menu.sh Menu.sh.bak")
        os.system("git checkout origin/main -- Menu.sh && chmod +x Menu.sh")
        bot.edit_message_text("✅ **Лаунчер оновлено!**\nБекап створено, права (chmod +x) відновлено.", 
                              call.message.chat.id, call.message.message_id, reply_markup=get_update_keyboard(), parse_mode="Markdown")

    elif call.data == "rb_bot":
        if os.path.exists("light_bot.py.bak"):
            send_tech_info("↩️ **Відкат бота...**\nВідновлюю попередню версію з бекапу.")
            os.system("cp light_bot.py.bak light_bot.py")
            os._exit(0)
        else: bot.answer_callback_query(call.id, "❌ Бекап не знайдено!", show_alert=True)

    elif call.data.startswith("notify_"):
        settings['notifications'] = (call.data == "notify_on")
        save_settings(settings)
        if settings['notifications']:
            markup = types.InlineKeyboardMarkup(row_width=2)
            btns = [types.InlineKeyboardButton(city, callback_data=f"city_{city}") for city in CITY_SOURCES.keys()]
            markup.add(*btns)
            bot.edit_message_text("🏙️ Оберіть місто:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        else: 
            bot.edit_message_text("🔕 Сповіщення вимкнено.", call.message.chat.id, call.message.message_id)

    elif call.data.startswith("city_"):
        city = call.data.split("_")[1]
        settings['city'] = city
        save_settings(settings)
        try:
            r = requests.get(CITY_SOURCES[city], timeout=15)
            data = r.json()
            with open(LOCAL_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            queues = sorted([k for k in data.keys() if 'GPV' in k] or [k for k in data.get('fact', {}).get('data', {}).get(list(data.get('fact', {}).get('data', {}).keys() or [''])[0], {}).keys() if 'GPV' in k])
            markup = types.InlineKeyboardMarkup(row_width=3)
            btns = [types.InlineKeyboardButton(text=q.replace('GPV', ''), callback_data=f"queue_{q}") for q in queues]
            markup.add(*btns)
            bot.edit_message_text(f"🔢 Черга для м. {city}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception as e: 
            send_tech_info(f"🔴 **Помилка завантаження міст:** {e}")

    elif call.data.startswith("queue_"):
        settings['queue'] = call.data.split("_")[1]
        save_settings(settings)
        bot.edit_message_text(f"✅ **Збережено!**\n📍 {settings['city']}, Черга: {settings['queue'].replace('GPV', '')}", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- [ СТАТУС ТА ДОПОМОГА ] ---
def get_battery_info():
    try:
        result = subprocess.check_output(["termux-battery-status"], text=True)
        data = json.loads(result)
        raw_temp = data.get("temperature", 0)
        corrected_temp = round(raw_temp - 2, 1) if isinstance(raw_temp, (int, float)) else "?"
        return {
            "plugged": data.get("plugged", "UNPLUGGED") != "UNPLUGGED",
            "percent": data.get("percentage", "?"),
            "temp": corrected_temp
        }
    except: return None

@bot.message_handler(func=lambda message: message.text in ["/help", "❓"])
def help_command(message):
    is_admin_private = (message.from_user.id in ADMIN_IDS and message.chat.type == 'private')
    help_text = f"📜 **Команди (v{VERSION}):**\n• 💡 або 🛎️ — Статус світла.\n• ❓ `/help` — Допомога."
    if is_admin_private:
        help_text += "\n\n🛠️ **Адмін-панель:**\n• ⚙️ `/set` — Налаштування бота."
    help_text += f"\n\n🔗 [GitHub]({REPO_URL}) | ☕ [На каву]({MONO_URL})"
    bot.reply_to(message, help_text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(func=lambda message: True)    
def handle_message(message):
    text = message.text
    if any(x in text for x in ["💡", "🛎️", "Є світло?"]) or text == "/status":
        info = get_battery_info()
        if info:
            status_text = "💡 **Світло є**" if info["plugged"] else "🕯️ **Світла немає**"
            bot.reply_to(message, f"{status_text}\n🔋: {info['percent']}% | 🌡️: ~{info['temp']}°C", parse_mode="Markdown")

# --- [ ПЕРШИЙ ЗАПУСК ] ---
def first_run_check():
    marker_file = '.installed'
    if not os.path.exists(marker_file):
        try:
            admin_mention = f"[@admin](tg://user?id={ADMIN_IDS[0]})" if ADMIN_IDS else "Адміністратор"
            msg_admin = (
                f"🛠 **Система активована!**\n\n"
                f"👤 {admin_mention}, будь ласка, напишіть боту в приватні повідомлення "
                f"та натисніть **/start**, щоб мати можливість отримувати технічні сповіщення "
                f"та керувати налаштуваннями."
            )
            bot.send_message(CHAT_ID, msg_admin, parse_mode="Markdown")

            help_text = (
                f"📜 **Вітаємо! Бот для моніторингу світла готовий.**\n\n"
                f"Ви можете використовувати наступні емодзі для перевірки стану:\n"
                f"• 💡 або 🛎️ — Дізнатися, чи є світло зараз\n"
                f"• ❓ `/help` — Виклик цієї довідки\n\n"
                f"📢 Всі сповіщення про зміну стану будуть приходити сюди автоматично."
            )
            bot.send_message(CHAT_ID, help_text, parse_mode="Markdown")

            with open(marker_file, 'w') as f:
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            print(f"[ERROR] Не вдалося відправити привітальні повідомлення: {e}")

if __name__ == "__main__":
    subprocess.run(["termux-wake-lock"])
    
    # Виклик перевірки першого запуску
    first_run_check()
    
    # Повідомляємо адміна про запуск у приват
    send_tech_info(f"✅ **Бот запущений!**\nВерсія: `{VERSION}`\nWake Lock: Active")
    
    threading.Thread(target=monitoring_loop, daemon=True).start()
    while True:
        try: bot.infinity_polling()
        except: time.sleep(5)
