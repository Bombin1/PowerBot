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
    """Зчитує дані ТІЛЬКИ для поточного дня через ключ today"""
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
        if time_zones and key in time_zones:
            t_start, t_end = time_zones[key][1], time_zones[key][2]
        else:
            t_start, t_end = f"{i-1:02d}:00", f"{i:02d}:00"

        if status != current_status:
            if current_status is not None:
                schedule_blocks.append((current_status, start_time, t_start))
            current_status, start_time = status, t_start
        if i == 24:
            schedule_blocks.append((current_status, start_time, t_end))

    text = ""
    for status, s, e in schedule_blocks:
        if status == "no":
            icon, desc = "🔴", "Відключення"
        elif status == "yes":
            icon, desc = "🟢", "Світло Є"
        else:
            icon = "🟡"
            desc = time_types.get(status, "Можливе відключення")
        text += f"{icon} **{s} - {e}** — {desc}\n"
    
    return text

# --- [ ФОНОВІ ПРОЦЕСИ ] ---

def monitoring_loop():
    global last_power_state
    last_check_hour = -1
    last_schedule_text = "" 
    
    info = get_battery_info()
    if info: last_power_state = info["plugged"]
    
    while True:
        try:
            # 1. СВІТЛО (кожні 30 сек)
            info = get_battery_info()
            if info and last_power_state is not None and info["plugged"] != last_power_state:
                text = "💡 **Світло з'явилось!**" if info["plugged"] else "🕯️ **Світло зникло!**"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                last_power_state = info["plugged"]
            
            # 2. ГРАФІК (раз на годину)
            now = datetime.now()
            settings = load_settings()
            
            if settings.get("notifications") and settings.get("city"):
                if now.hour != last_check_hour:
                    try:
                        r = requests.get(CITY_SOURCES[settings['city']], timeout=15)
                        if r.status_code == 200:
                            data = r.json()
                            current_schedule = format_schedule(data, settings['queue'])
                            
                            # Публікуємо ТІЛЬКИ якщо текст змінився
                            if current_schedule and current_schedule != last_schedule_text:
                                q_num = settings['queue'].replace('GPV', '')
            
                                # Визначаємо заголовок (нічне вікно 00:00 - 04:00 для нових графіків)
                                if not last_schedule_text or (0 <= now.hour < 4):
                                    header_type = "📅 **Графік на сьогодні**"
                                else:
                                    header_type = "⚠️ **Графік оновлено**"
            
                                header = f"{header_type} ({q_num}):"
            
                                bot.send_message(CHAT_ID, f"{header}\n\n{current_schedule}", parse_mode="Markdown")
                                
                                last_schedule_text = current_schedule
                                with open(LOCAL_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                                    json.dump(data, f, ensure_ascii=False)
                            
                            last_check_hour = now.hour
                    except Exception as sched_e:
                        print(f"Помилка графіка: {sched_e}")

            time.sleep(30)
        except Exception as e:
            print(f"Помилка моніторингу: {e}")
            time.sleep(10)

# --- [ АДМІН-МЕНЮ /SET ] ---

def get_update_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🤖 Бот", callback_data="upd_bot"),
        types.InlineKeyboardButton("🛫 Лаунчер", callback_data="upd_launcher")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_set"))
    return markup

def get_rollback_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🤖 Бот", callback_data="rb_bot"),
        types.InlineKeyboardButton("🛫 Лаунчер", callback_data="rb_launcher")
    )
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main_set"))
    return markup
@bot.message_handler(func=lambda message: message.text in ["/set", "⚙️"])    
def admin_settings(message):
    if message.from_user.id not in ADMIN_IDS: return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📊 Графік", callback_data="set_graph"))
    markup.add(types.InlineKeyboardButton("🔄 Оновлення", callback_data="exec_update"),
               types.InlineKeyboardButton("↩️ Відкат", callback_data="exec_rollback"))
    
    bot.send_message(message.chat.id, "🛠️ **Адмін-панель:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    settings = load_settings()

    # --- ГОЛОВНЕ МЕНЮ /SET ---
    if call.data == "set_graph":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Увімкнути", callback_data="notify_on"),
                   types.InlineKeyboardButton("❌ Вимкнути", callback_data="notify_off"))
        bot.edit_message_text("Дзвоник сповіщень про графік:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "exec_update":
        if call.from_user.id in ADMIN_IDS:
            bot.edit_message_text("🔄 **Що саме оновити?**", call.message.chat.id, call.message.message_id, reply_markup=get_update_keyboard(), parse_mode="Markdown")

    elif call.data == "exec_rollback":
        if call.from_user.id in ADMIN_IDS:
            bot.edit_message_text("↩️ **Що саме відкотити?**", call.message.chat.id, call.message.message_id, reply_markup=get_rollback_keyboard(), parse_mode="Markdown")

    elif call.data == "back_to_main_set":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📊 Графік", callback_data="set_graph"))
        markup.add(types.InlineKeyboardButton("🔄 Оновлення", callback_data="exec_update"),
                   types.InlineKeyboardButton("↩️ Відкат", callback_data="exec_rollback"))
        bot.edit_message_text("🛠️ **Адмін-панель:**", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    # --- ЛОГІКА ОНОВЛЕННЯ ---
    elif call.data == "upd_bot":
        bot.edit_message_text("🚀 **Робимо бекап та оновлюємо бота...**\nЗачекайте 10 сек.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        os.system("cp light_bot.py light_bot.py.bak")
        os.system("git checkout origin/main -- light_bot.py")
        os._exit(0)

    elif call.data == "upd_launcher":
        bot.edit_message_text("🛫 **Оновлюю лаунчер...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        os.system("cp Menu.sh Menu.sh.bak")
        os.system("git checkout origin/main -- Menu.sh && chmod +x Menu.sh")
        bot.edit_message_text("✅ **Лаунчер оновлено!**\nБекап створено, права (chmod +x) відновлено.", 
                              call.message.chat.id, call.message.message_id, reply_markup=get_update_keyboard(), parse_mode="Markdown")

    # --- ЛОГІКА ВІДКАТУ ---
    elif call.data == "rb_bot":
        if os.path.exists("light_bot.py.bak"):
            bot.edit_message_text("↩️ **Відновлюю бота з бекапу...**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            os.system("cp light_bot.py.bak light_bot.py")
            os._exit(0)
        else: bot.answer_callback_query(call.id, "❌ Бекап бота не знайдено!", show_alert=True)

    elif call.data == "rb_launcher":
        if os.path.exists("Menu.sh.bak"):
            os.system("cp Menu.sh.bak Menu.sh && chmod +x Menu.sh")
            bot.edit_message_text("✅ **Лаунчер відновлено!**\nПрава доступу відновлено.", 
                                  call.message.chat.id, call.message.message_id, reply_markup=get_rollback_keyboard(), parse_mode="Markdown")
        else: bot.answer_callback_query(call.id, "❌ Бекап лаунчера не знайдено!", show_alert=True)

    # --- НАЛАШТУВАННЯ МІСТ ТА ЧЕРГ (Твій робочий код) ---
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
        bot.answer_callback_query(call.id, f"📥 Завантаження для м. {city}...")
        try:
            r = requests.get(CITY_SOURCES[city], timeout=15)
            r.encoding = 'utf-8'
            data = r.json()
            with open(LOCAL_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            queues = [k for k in data.keys() if 'GPV' in k]
            if not queues and 'fact' in data:
                fact_data = data['fact'].get('data', {})
                if fact_data:
                    first_ts = list(fact_data.keys())[0]
                    queues = [k for k in fact_data[first_ts].keys() if 'GPV' in k]
            queues.sort()
            markup = types.InlineKeyboardMarkup(row_width=3)
            btns = [types.InlineKeyboardButton(text=q.replace('GPV', ''), callback_data=f"queue_{q}") for q in queues]
            markup.add(*btns)
            bot.edit_message_text(f"🔢 Оберіть чергу для м. {city}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception as e: bot.send_message(call.message.chat.id, f"❌ Помилка: {e}")

    elif call.data.startswith("queue_"):
        queue_key = call.data.split("_")[1]
        settings['queue'] = queue_key
        save_settings(settings)
        bot.answer_callback_query(call.id, "✅ Збережено!")
        bot.edit_message_text(f"✅ **Налаштування завершено!**\n📍 Місто: {settings['city']}\n🔢 Черга: {queue_key.replace('GPV', '')}", 
                              call.message.chat.id, call.message.message_id, parse_mode="Markdown")

# --- [ ІСНУЮЧІ ФУНКЦІЇ БАТАРЕЇ ТА ДОПОМОГИ ] ---

def send_error_to_admin(error_text):
    try:
        if ADMIN_IDS:
            bot.send_message(ADMIN_IDS[0], f"⚠️ **Критична помилка:**\n`{error_text}`", parse_mode="Markdown")
    except: pass

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
    user_id = message.from_user.id
    help_text = "📜 **Команди:**\n• 💡 або 🛎️ — Статус світла.\n• ❓ `/help` — Допомога."
    if user_id in ADMIN_IDS:
        help_text += "\n\n🛠️ **Адмін-панель:**\n• ⚙️ `/set` — Налаштування графіка та бота."
    
    help_text += f"\n\n🔗 [GitHub]({REPO_URL}) | ☕ [На каву]({MONO_URL})"
    bot.reply_to(message, help_text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(func=lambda message: True)    
def handle_message(message):
    text = message.text
    if any(x in text for x in ["💡", "🛎️", "Є світло?"]) or text == "/status":
        info = get_battery_info()
        if info:
            if info["plugged"]:
                status_text = "💡 **Світло є**"
            else:
                status_text = "🕯️ **Світла немає**"
            
            percent = info['percent']
            reply = f"{status_text}\n🔋: {percent}% | 🌡️: ~{info['temp']}°C"        
            bot.reply_to(message, reply, parse_mode="Markdown")

# --- [ СИСТЕМНІ ФУНКЦІЇ ] ---

def update_bot(message):
    """Просто вимикає бота, а menu.sh підхопить і оновить код силоміць"""
    if message.from_user.id not in ADMIN_IDS: return
    try:
        bot.reply_to(message, "🚀 Виконую оновлення... Зачекайте 10-15 секунд.")
        # Завершуємо процес. Bash-скрипт побачить це і зробить reset --hard
        os._exit(0) 
    except Exception as e:
        bot.reply_to(message, f"❌ Помилка: {e}")

def rollback_bot(message):
    """Повертає бекап, якщо він є, і перезапускає бота"""
    if message.from_user.id not in ADMIN_IDS: return
    if os.path.exists("light_bot_backup.py"):
        subprocess.run(["cp", "light_bot_backup.py", sys.argv[0]])
        bot.reply_to(message, "🔙 Відкат виконано! Перезапуск...")
        os._exit(0)
    else:
        bot.reply_to(message, "❌ Файл бекапу не знайдено.")

if __name__ == "__main__":
    subprocess.run(["termux-wake-lock"])
    threading.Thread(target=monitoring_loop, daemon=True).start()
    while True:
        try: bot.infinity_polling()
        except: time.sleep(5)
