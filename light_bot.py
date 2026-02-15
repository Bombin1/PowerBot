import telebot
import subprocess
import json
import time
import threading
import os
import sys

# --- [ РОБОТА З КОНФІГ-ФАЙЛОМ ] ---
try:
    # Імпортуємо налаштування з локального файлу, створеного Menu.sh
    from config import BOT_TOKEN, ADMIN_IDS, CHAT_ID
except ImportError:
    print("❌ Помилка: Файл config.py не знайдено! Запустіть Menu.sh для налаштування.")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)
last_power_state = None
REPO_URL = "https://github.com/Bombin1/PowerBot.git" 
MONO_URL = "https://send.monobank.ua/jar/8WFAPWLdPu"

# --- [ ДОПОМІЖНІ ФУНКЦІЇ ] ---

def send_error_to_admin(error_text):
    """Надсилає повідомлення про помилку першому адміну в списку"""
    try:
        if ADMIN_IDS:
            bot.send_message(ADMIN_IDS[0], f"⚠️ **Критична помилка:**\n`{error_text}`", parse_mode="Markdown")
    except Exception:
        pass

def get_battery_info():
    """Отримує дані батареї через Termux з корекцією температури"""
    try:
        result = subprocess.check_output(["termux-battery-status"], text=True)
        data = json.loads(result)
        
        # Корекція температури (-5 градусів)
        raw_temp = data.get("temperature", 0)
        corrected_temp = round(raw_temp - 5, 1) if isinstance(raw_temp, (int, float)) else "?"
        
        return {
            "plugged": data.get("plugged", "UNPLUGGED") != "UNPLUGGED",
            "percent": data.get("percentage", "?"),
            "temp": corrected_temp
        }
    except Exception as e:
        print(f"Помилка батареї: {e}")
        return None

def monitoring_loop():
    """Фоновий процес моніторингу світла"""
    global last_power_state
    info = get_battery_info()
    if info:
        last_power_state = info["plugged"]
    
    while True:
        try:
            info = get_battery_info()
            if info and last_power_state is not None and info["plugged"] != last_power_state:
                text = "💡 **Світло з'явилось!**" if info["plugged"] else "🕯️ **Світло зникло!**"
                bot.send_message(CHAT_ID, text, parse_mode="Markdown")
                last_power_state = info["plugged"]
            time.sleep(30)
        except Exception as e:
            send_error_to_admin(f"Помилка моніторингу: {e}")
            time.sleep(10)

# --- [ СИСТЕМА ОНОВЛЕННЯ ТА ВІДКАТУ ] ---

@bot.message_handler(commands=['update'])
def update_bot(message):
    """Оновлення з GitHub із автоматичним бекапом"""
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас немає прав.")
        return

    bot.reply_to(message, "📦 Створюю локальний бекап та завантажую оновлення...")
    try:
        subprocess.run(["cp", sys.argv[0], "light_bot_backup.py"])
        subprocess.check_output(["git", "pull"], text=True)
        check_code = subprocess.run([sys.executable, "-m", "py_compile", sys.argv[0]])
        
        if check_code.returncode == 0:
            bot.reply_to(message, "✅ Оновлено! Перезавантаження...")
            os.execv(sys.executable, ['python'] + sys.argv)
        else:
            subprocess.run(["cp", "light_bot_backup.py", sys.argv[0]])
            bot.reply_to(message, "❌ Помилка в коді! Повернено бекап.")
    except Exception as e:
        bot.reply_to(message, f"❌ Помилка: {e}")
        send_error_to_admin(f"Помилка оновлення: {e}")

@bot.message_handler(commands=['rollback'])
def rollback_bot(message):
    """Ручний відкат до попередньої версії"""
    if message.from_user.id not in ADMIN_IDS:
        return

    if os.path.exists("light_bot_backup.py"):
        bot.reply_to(message, "🔙 Повертаю попередню версію з бекапу...")
        subprocess.run(["cp", "light_bot_backup.py", sys.argv[0]])
        os.execv(sys.executable, ['python'] + sys.argv)
    else:
        bot.reply_to(message, "❌ Файл бекапу не знайдено.")

# --- [ ОБРОБКА КОМАНД ТА ПРИВІТАННЯ ] ---

def get_help_text(user_id):
    """Генерує текст допомоги з логічним розділенням блоків"""
    # 1. Основні команди для всіх
    help_text = (
        "📜 **Команди:**\n"
        "• 💡 або 🛎️ — Статус світла та батареї.\n"
        "• ❓ `/help` — Допомога."
    )
    
    # 2. Адмін-панель (якщо користувач адмін)
    if user_id in ADMIN_IDS or user_id == 0: # 0 використовується для системного привітання
        help_text += "\n\n🛠️ **Адмін-панель:**\n🔄 `/update` | 🔙 `/rollback`"
    
    # 3. Посилання внизу (Markdown формат)
    help_text += (
        "\n\n"
        f"🔗 [GitHub проєкту]({REPO_URL})\n"
        f"☕ [На каву автору]({MONO_URL})"
    )
    return help_text

@bot.message_handler(commands=['help'])
def help_command(message):
    """Меню допомоги за запитом"""
    text = get_help_text(message.from_user.id)
    bot.reply_to(message, text, parse_mode="Markdown", disable_web_page_preview=True)

def send_welcome_message():
    """Надсилає привітання в групу лише при першому запуску"""
    first_run_file = ".first_run_completed"
    if not os.path.exists(first_run_file):
        try:
            welcome_text = "🚀 **Бот успішно налаштований та запущений!**\n\n" + get_help_text(0)
            bot.send_message(CHAT_ID, welcome_text, parse_mode="Markdown", disable_web_page_preview=True)
            with open(first_run_file, "w") as f:
                f.write("done")
        except Exception as e:
            print(f"Помилка привітання: {e}")

@bot.message_handler(func=lambda message: True)    
def handle_message(message):
    """Обробка тригерів статусу"""
    text = message.text.lower().strip()
    if any(x in text for x in ["💡", "🛎️"]) or text == "/status":
        info = get_battery_info()
        if info:
            status = "Є" if info["plugged"] else "НЕМАЄ"
            icon = "💡" if info["plugged"] else "🕯️"
            try:
                percent = int(info['percent'])
                batt_icon = "🪫" if percent <= 50 else "🔋"
            except:
                batt_icon = "🔋"
                
            reply = (f"{icon} **Світло {status}**\n"
                     f"{batt_icon}: {info['percent']}% | 🌡️: ~{info['temp']}°C")
            bot.reply_to(message, reply, parse_mode="Markdown")

if __name__ == "__main__":
    subprocess.run(["termux-wake-lock"])
    threading.Thread(target=monitoring_loop, daemon=True).start()
    
    # Перевірка на перший запуск
    send_welcome_message()
    
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            send_error_to_admin(f"Polling error: {e}")
            time.sleep(5)
