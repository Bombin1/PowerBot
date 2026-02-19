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
    """Об'єднує години в блоки та формує текст розкладу"""
    time_zones = data.get("time_zone", {})
    time_types = data.get("time_type", {})
    queue_data = data.get(queue_name, {})
    
    if not queue_data:
        return "❌ Дані для вашої черги не знайдені."

    schedule_blocks = []
    current_status = None
    start_time = None
    
    # Цикл по 24 годинах
    for i in range(1, 25):
        key = str(i)
        status = queue_data.get(key)
        
        # Визначаємо часовий проміжок
        if time_zones:
            t_start = time_zones[key][1]
            t_end = time_zones[key][2]
        else:
            t_start = f"{i-1:02d}:00"
            t_end = f"{i:02d}:00"

        if status != current_status:
            if current_status is not None:
                schedule_blocks.append((current_status, start_time, t_start))
            current_status = status
            start_time = t_start
        
        if i == 24:
            schedule_blocks.append((current_status, start_time, t_end))

    # Формуємо текст
    text = f"📅 **Графік на сьогодні ({queue_name}):**\n\n"
    for status, s, e in schedule_blocks:
        icon = "🟢" if status == "yes" else "🔴" if status == "no" else "🟡"
        desc = time_types.get(status, status)
        text += f"{icon} **{s} - {e}** — {desc}\n"
    
    return text

# --- [ ФОНОВІ ПРОЦЕСИ ] ---

def monitoring_loop():
    global last_power_state
    info = get_battery_info()
    if info: last_power_state = info["plugged"]
    
    while True:
        try:
            # 1. Моніторинг світла (існуючий)
            info = get_battery_info()
            if info and last_power_state is not None and info["plugged"] != last_power_state:
                text = "💡 **Світло з'явилось!**" if info["plugged"] else "🕯️ **Світло зникло!**"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                last_power_state = info["plugged"]
            
            # 2. Моніторинг графіка (новий)
            settings = load_settings()
            if settings.get("notifications") and settings.get("city"):
                now = datetime.now()
                # Пост о 06:00 або перевірка щогодини на зміни
                if now.minute == 0 or not os.path.exists(LOCAL_SCHEDULE_FILE):
                    check_schedule_updates(settings)

            time.sleep(30)
        except Exception as e:
            send_error_to_admin(f"Помилка моніторингу: {e}")
            time.sleep(10)

def check_schedule_updates(settings):
    try:
        url = CITY_SOURCES[settings['city']]
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            new_data = r.json()
            new_hash = hash(str(new_data.get(settings['queue'])))
            
            # Перевірка на 06:00 ранку
            is_morning = datetime.now().hour == 6 and datetime.now().minute < 5
            
            if new_hash != settings.get("last_hash") or is_morning:
                text = format_schedule(new_data, settings['queue'])
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                
                settings['last_hash'] = new_hash
                save_settings(settings)
                with open(LOCAL_SCHEDULE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(new_data, f)
    except:
        pass

# --- [ АДМІН-МЕНЮ /SET ] ---

@bot.message_handler(commands=['set'])
def admin_settings(message):
    if message.from_user.id not in ADMIN_IDS: return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_graph = types.InlineKeyboardButton("📊 Графік", callback_data="set_graph")
    btn_upd = types.InlineKeyboardButton("🔄 Оновити бот", callback_data="exec_update")
    btn_roll = types.InlineKeyboardButton("🔙 Відкатитись", callback_data="exec_rollback")
    
    markup.add(btn_graph)
    markup.add(btn_upd, btn_roll)
    bot.send_message(message.chat.id, "🛠️ **Адмін-панель:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    settings = load_settings()

    if call.data == "set_graph":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Увімкнути", callback_data="notify_on"),
                   types.InlineKeyboardButton("❌ Вимкнути", callback_data="notify_off"))
        bot.edit_message_text("Дзвоник сповіщень про графік:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("notify_"):
        settings['notifications'] = (call.data == "notify_on")
        save_settings(settings)
        if settings['notifications']:
            # Показуємо міста по 2 в ряд
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
            r = requests.get(CITY_SOURCES[city])
            data = r.json()
            
            # ВИПРАВЛЕННЯ: Шукаємо тільки ключі, що починаються на GPV
            # Це відсіє regionId, fact, preset та інше сміття
            queues = [k for k in data.keys() if k.startswith("GPV")]
            
            # Сортуємо, щоб черги йшли по порядку: 1, 2, 3...
            queues.sort()
            
            markup = types.InlineKeyboardMarkup(row_width=3)
            # На кнопці показуємо назву без "GPV", але в callback передаємо повний ключ
            btns = [types.InlineKeyboardButton(q.replace("GPV", ""), callback_data=f"queue_{q}") for q in queues]
            markup.add(*btns)
            bot.edit_message_text(f"🔢 Оберіть чергу для м. {city}:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception as e:
            print(f"Error: {e}") # Для відладки в консолі Termux
            bot.send_message(call.message.chat.id, "❌ Помилка завантаження черг.")

    elif call.data.startswith("queue_"):
        # Витягуємо назву черги. split("_", 1)[1] гарантує, що ми візьмемо 
        # все, що йде після першого підкреслення (наприклад, "GPV4.1")
        queue_id = call.data.split("_", 1)[1]
        
        settings['queue'] = queue_id
        save_settings(settings)
        
        # Для відображення прибираємо GPV, щоб було "Черга: 4.1"
        display_name = queue_id.replace("GPV", "")
        
        bot.edit_message_text(
            f"✅ Налаштовано!\n🏙️ Місто: {settings['city']}\n🔢 Черга: {display_name}", 
            call.message.chat.id, 
            call.message.message_id
        )

    elif call.data == "exec_update":
        update_bot(call.message)
    elif call.data == "exec_rollback":
        rollback_bot(call.message)

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

@bot.message_handler(commands=['help'])
def help_command(message):
    user_id = message.from_user.id
    help_text = "📜 **Команди:**\n• 💡 або 🛎️ — Статус світла.\n• ❓ `/help` — Допомога."
    if user_id in ADMIN_IDS:
        help_text += "\n\n🛠️ **Адмін-панель:**\n• `/set` — Налаштування графіка та бота."
    
    help_text += f"\n\n🔗 [GitHub]({REPO_URL}) | ☕ [На каву]({MONO_URL})"
    bot.reply_to(message, help_text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(func=lambda message: True)    
def handle_message(message):
    text = message.text.lower().strip()
    if any(x in text for x in ["💡", "🛎️"]) or text == "/status":
        info = get_battery_info()
        if info:
            status = "Є" if info["plugged"] else "НЕМАЄ"
            icon = "💡" if info["plugged"] else "🕯️"
            percent = info['percent']
            reply = f"{icon} **Світло {status}**\n🔋: {percent}% | 🌡️: ~{info['temp']}°C"
            
            # Додаємо графік до статусу, якщо він налаштований
            settings = load_settings()
            if settings.get("city") and os.path.exists(LOCAL_SCHEDULE_FILE):
                with open(LOCAL_SCHEDULE_FILE, 'r') as f:
                    data = json.load(f)
                    reply += "\n\n" + format_schedule(data, settings['queue'])
            
            bot.reply_to(message, reply, parse_mode="Markdown")

# --- [ СИСТЕМНІ ФУНКЦІЇ ] ---

# Обробка кнопки Оновити
@bot.callback_query_handler(func=lambda call: call.data == 'update')
def update_callback(call):
    try:
        bot.answer_callback_query(call.id, "⏳ Оновлення...")
        # Виконуємо команду git pull для завантаження останніх змін з репозиторію
        import subprocess
        result = subprocess.run(['git', 'pull'], capture_output=True, text=True)
        
        if "Already up to date" in result.stdout:
            bot.send_message(call.message.chat.id, "✅ У вас вже встановлена остання версія.")
        else:
            bot.send_message(call.message.chat.id, "🚀 Бот оновлений! Перезавантажте його через Menu.sh")
            
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Помилка оновлення: {e}")

# Обробка кнопки Відкотити (Rollback)
@bot.callback_query_handler(func=lambda call: call.data.startswith('region_'))
def select_queue_callback(call):
    region_id = call.data.split('_')[1]
    url = REGIONS.get(region_id)
    if url:
        try:
            data = requests.get(url).json()
            # Фільтруємо: тільки ключі, що починаються на GPV
            queues = [k for k in data.keys() if k.startswith('GPV')]
            
            markup = types.InlineKeyboardMarkup(row_width=2)
            for q in queues:
                # Відображаємо "4.1", але передаємо "GPV4.1"
                markup.add(types.InlineKeyboardButton(
                    text=q.replace('GPV', ''), 
                    callback_data=f"queue_{region_id}_{q}"
                ))
            bot.edit_message_text("🔢 Оберіть чергу:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        except:
            bot.answer_callback_query(call.id, "❌ Помилка завантаження JSON")
