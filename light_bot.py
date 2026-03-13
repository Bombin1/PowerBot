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
VERSION = "3.3"  # Поточна версія бота
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

def set_bot_commands():
    # Команди для адмінів (бачать у приваті)
    admin_commands = [
        types.BotCommand("status", "💡 Перевірити наявність"),
        types.BotCommand("set", "⚙️ Налаштування"),
        types.BotCommand("help", "ℹ️ Інфо")
    ]
    # Команди для загальних чатів
    group_commands = [
        types.BotCommand("status", "💡 Перевірити наявність"),
        types.BotCommand("help", "ℹ️ Інфо")
    ]
    
    # Реєструємо меню для кожного адміна окремо
    for admin_id in ADMIN_IDS:
        try:
            bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(admin_id))
        except:
            pass
    
    # Реєструємо меню для всіх груп
    try:
        bot.set_my_commands(group_commands, scope=types.BotCommandScopeAllGroupChats())
    except:
        pass

# --- [ ЦЕНТРАЛІЗОВАНІ ТЕХНІЧНІ ПОВІДОМЛЕННЯ ] ---
def send_tech_info(text):
    """Надсилає технічну інформацію ТІЛЬКИ адмінам у приват"""
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            print(f"[LOG] Не вдалося надіслати в приват {admin_id}.")

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
    try:
        clean_v = "".join(filter(lambda x: x.isdigit() or x == '.', str(v).strip()))
        return tuple(map(int, clean_v.split(".")))
    except:
        return (0, 0)

def check_updates_for_admin(manual=False):
    global last_update_check_day, last_notified_version
    current_day = datetime.now().date()
    
    if not manual and last_update_check_day == current_day: 
        return

    try:
        timestamp = int(time.time())
        v_url = f"{VERSION_URL}?t={timestamp}"
        headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        response = requests.get(v_url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            if manual: send_tech_info("❌ GitHub не відповів.")
            return
            
        github_version = "".join(filter(lambda x: x.isdigit() or x == '.', response.text.strip()))
        
        if manual:
            send_tech_info(f"🔍 **Результат перевірки:**\nGitHub: `{github_version}` | Ви: `{VERSION}`")

        if version_tuple(github_version) > version_tuple(VERSION):
            if not manual and last_notified_version == github_version:
                return
            send_tech_info(f"🚀 **Доступне оновлення!**\n\nНова версія: `{github_version}`\nВстановіть через `/set` -> Оновлення")
            last_notified_version = github_version
        elif manual:
            send_tech_info(f"✅ **Версія актуальна.**")
        
        if not manual:
            last_update_check_day = current_day
    except Exception as e:
        if manual: send_tech_info(f"🔴 Помилка оновлення: {e}")

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
                                header = "📅 **Графік на сьогодні**" if not last_schedule_text or (0 <= now.hour < 4) else "⚠️ **Графік оновлено**"
                                bot.send_message(CHAT_ID, f"{header} ({q_num}):\n\n{current_schedule}", parse_mode="Markdown")
                                last_schedule_text = current_schedule
                            last_check_hour = now.hour
                    except: pass
            time.sleep(30)
        except Exception as e:
            time.sleep(10)

# --- [ КЛАВІАТУРИ ДЛЯ АДМІНКИ ] ---
def get_update_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔍 Перевірити зараз", callback_data="manual_check_now"))
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
    
# --- [ КЛАВІАТУРА ] ---
def get_main_keyboard():
    # is_persistent=True — щоб кнопка завжди була під полем вводу
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, is_persistent=True)
    markup.add(types.KeyboardButton("💡 Перевірити наявність"))
    return markup

# --- [ ОБРОБНИКИ КОМАНД ] ---
@bot.message_handler(commands=['help'])
def help_command(message):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    
    is_admin = (message.from_user.id in ADMIN_IDS and message.chat.type == 'private')
    help_text = f"📜 **Інфо (v{VERSION}):**\n\n• `/status` — Перевірити світло 💡\n• `/help` — Допомога ℹ️"
    if is_admin:
        help_text += "\n• `/set` — Налаштування ⚙️"
    
    help_text += f"\n\n🔗 [GitHub]({REPO_URL}) | ☕ [На каву]({MONO_URL})"
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['status'])
@bot.message_handler(func=lambda message: message.text == "💡 Перевірити наявність")
def handle_status(message):
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    
    info = get_battery_info()
    if info:
        status_text = "💡 **Світло є**" if info["plugged"] else "🕯️ **Світла немає**"
        bot.send_message(
            message.chat.id, 
            f"{status_text}\n🔋: {info['percent']}% | 🌡️: ~{info['temp']}°C", 
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@bot.message_handler(commands=['set'])
def admin_settings(message):
    if message.chat.type != 'private' or message.from_user.id not in ADMIN_IDS:
        return
    try: bot.delete_message(message.chat.id, message.message_id)
    except: pass
    
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
        bot.edit_message_text("Сповіщення про графік:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "exec_update":
        bot.edit_message_text("🔄 **Що оновити?**", call.message.chat.id, call.message.message_id, reply_markup=get_update_keyboard(), parse_mode="Markdown")

    elif call.data == "back_to_main_set":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📊 Графік", callback_data="set_graph"))
        markup.add(types.InlineKeyboardButton("🔄 Оновлення", callback_data="exec_update"),
                   types.InlineKeyboardButton("↩️ Відкат", callback_data="exec_rollback"))
        bot.edit_message_text("🛠️ **Адмін-панель:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "manual_check_now":
        bot.answer_callback_query(call.id, "🔍 Перевіряю...")
        check_updates_for_admin(manual=True)

    elif call.data == "upd_bot":
        send_tech_info("🚀 Оновлюю бота...")
        with open(".update_bot", "w") as f: f.write("1")
        os._exit(0)

    elif call.data == "upd_launcher":
        send_tech_info("🛫 Оновлюю лаунчер...")
        with open(".update_launcher", "w") as f: f.write("1")
        os._exit(0)

    elif call.data == "rb_bot":
        if os.path.exists("light_bot_backup.py"):
            send_tech_info("↩️ Відкат бота...")
            with open(".rollback_bot", "w") as f: f.write("1")
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
        else: bot.edit_message_text("🔕 Вимкнено.", call.message.chat.id, call.message.message_id)

    elif call.data.startswith("city_"):
        city = call.data.split("_")[1]
        settings['city'] = city
        save_settings(settings)
        try:
            r = requests.get(CITY_SOURCES[city], timeout=15)
            data = r.json()
            queues = sorted([k for k in data.keys() if 'GPV' in k] or [k for k in data.get('fact', {}).get('data', {}).get(list(data.get('fact', {}).get('data', {}).keys() or [''])[0], {}).keys() if 'GPV' in k])
            markup = types.InlineKeyboardMarkup(row_width=3)
            btns = [types.InlineKeyboardButton(text=q.replace('GPV', ''), callback_data=f"queue_{q}") for q in queues]
            markup.add(*btns)
            bot.edit_message_text(f"🔢 Черга для м. {city}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except: send_tech_info("🔴 Помилка завантаження черг.")

    elif call.data.startswith("queue_"):
        settings['queue'] = call.data.split("_")[1]
        save_settings(settings)
        bot.edit_message_text(f"✅ **Збережено!**\n📍 {settings['city']}, Черга: {settings['queue'].replace('GPV', '')}", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")

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

# --- [ ПЕРШИЙ ЗАПУСК ] ---
def first_run_check():
    marker_file = '.installed'
    if not os.path.exists(marker_file):
        try:
            admin_mention = f"[@admin](tg://user?id={ADMIN_IDS[0]})" if ADMIN_IDS else "Адміністратор"
            msg = (f"🛠 **Система активована!**\n\n👤 {admin_mention}, напишіть боту в приват "
                   f"та натисніть **/start** (або оберіть меню), щоб керувати.")
            bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
            
            with open(marker_file, 'w') as f:
                f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        except: pass

if __name__ == "__main__":
    subprocess.run(["termux-wake-lock"])
    set_bot_commands()
    first_run_check()
    
    # Оновлюємо клавіатуру адміну в приваті при запуску
    for admin_id in ADMIN_IDS:
        try: 
            bot.send_message(admin_id, f"✅ **Бот запущений!** (v{VERSION})", 
                              parse_mode="Markdown", reply_markup=get_main_keyboard())
        except: 
            pass

    threading.Thread(target=monitoring_loop, daemon=True).start()
    while True:
        try: bot.infinity_polling()
        except: time.sleep(5)
