#!/data/data/com.termux/files/usr/bin/bash

# Шлях до файлів
BOT_FILE="$HOME/light_bot.py"
BACKUP_FILE="$HOME/light_bot_backup.py"
CONFIG_FILE="$HOME/config.py"
REPO_URL="https://github.com/Bombin1/PowerBot.git"

# --- [ БЛОК ІНСТАЛЯЦІЇ ] ---
install_logic() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "🆕 Перший запуск. Налаштування системи..."
        pkg update && pkg upgrade -y
        pkg install python git termux-api -y
        pip install pyTelegramBotAPI requests
        termux-wake-lock
        
        # Завантажуємо бота, якщо його нема
        if [ ! -f "$BOT_FILE" ]; then
            git clone "$REPO_URL" "$HOME/temp_repo"
            cp -r "$HOME/temp_repo/." "$HOME/"
            rm -rf "$HOME/temp_repo"
        fi

        echo "--- Налаштування конфігурації ---"
        read -p "Введіть TOKEN бота: " bot_token
        read -p "Введіть ID Адмінів (через кому): " admin_ids
        read -p "Введіть ID Групи: " chat_id

        echo "BOT_TOKEN = '$bot_token'" > "$CONFIG_FILE"
        echo "ADMIN_IDS = [$admin_ids]" >> "$CONFIG_FILE"
        echo "CHAT_ID = '$chat_id'" >> "$CONFIG_FILE"
        echo "✅ Система готова!"
    fi
}

show_menu() {
    clear
    echo "==============================="
    echo "   🤖 КЕРУВАННЯ POWER-BOT v2.1"
    echo "==============================="
    echo "1. Запустити бот (Захищений режим)"
    echo "2. Оновити бот (з GitHub + Backup)"
    echo "3. Скинути налаштування (Reset Config)"
    echo "4. Переглянути логи"
    echo "5. Вихід"
    echo "==============================="
}

# Запуск інсталятора перед меню
install_logic

while true; do
    show_menu
    read -p "Оберіть пункт [1-5]: " choice
    case $choice in
        1)
            echo "🚀 Запуск бота... (Ctrl+C для виходу в меню)"
            # Твій фірмовий «безсмертний» режим
            until python "$BOT_FILE"; do
                echo "⚠️ Бот впав!"
                if [ -f "$BACKUP_FILE" ]; then
                    echo "🔄 Відновлення з бекапу..."
                    cp "$BACKUP_FILE" "$BOT_FILE"
                    sleep 3
                else
                    echo "🚑 Спроба оновити код з GitHub..."
                    git pull origin main
                    sleep 5
                fi
            done
            ;;
        2)
            echo "🌐 Створення бекапу та оновлення..."
            cp "$BOT_FILE" "$BACKUP_FILE"
            git pull origin main
            read -p "✅ Готово. Бекап створено. Натисніть Enter.."
            ;;
        3)
            read -p "⚠️ Видалити конфіг і налаштувати заново? (y/n): " confirm
            if [ "$confirm" == "y" ]; then
                rm "$CONFIG_FILE"
                echo "♻️ Налаштування скинуто. Перезапустіть скрипт."
                exit 0
            fi
            ;;
        4)
            tail -n 20 "$HOME/bot_log.txt" 2>/dev/null || echo "❌ Логів немає."
            read -p "Натисніть Enter..."
            ;;
        5)
            echo "👋 Вихід."
            exit 0
            ;;
        *)
            echo "❌ Невірний вибір!"
            sleep 1
            ;;
    esac
done
