#!/data/data/com.termux/files/usr/bin/bash

# Шлях до файлів
BOT_FILE="$HOME/light_bot.py"
chmod +x "$HOME/menu.sh" 2>/dev/null
BACKUP_FILE="$HOME/light_bot_backup.py"
CONFIG_FILE="$HOME/config.py"
REPO_URL="https://github.com/Bombin1/PowerBot.git"

# --- [ БЛОК ІНСТАЛЯЦІЇ ТА АВТОЗАПУСКУ ] ---
install_logic() {
    # Перевірка та налаштування автозапуску в .bashrc
    if ! grep -q "menu.sh" ~/.bashrc; then
        echo "⚙️ Налаштування автозапуску при старті Termux..."
        echo "if [ -f ~/menu.sh ]; then ./menu.sh; fi" >> ~/.bashrc
    fi

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "🆕 Перший запуск. Налаштування системи..."
        pkg update && pkg upgrade -y
        pkg install python git termux-api -y
        pip install pyTelegramBotAPI requests
        termux-wake-lock
        
        # Правильне клонування репозиторію прямо в домашню папку
        if [ ! -d ".git" ]; then
            echo "📥 Клонування репозиторію..."
            git init .
            git remote add origin "$REPO_URL"
            git fetch
            git checkout -f main
        fi

        echo "--- Налаштування конфігурації ---"
        read -p "Введіть TOKEN бота: " bot_token
        read -p "Введіть ID Адмінів (через кому, напр: 123,456): " admin_ids
        read -p "Введіть ID Групи/Каналу (з мінусом, якщо треба): " chat_id

        echo "BOT_TOKEN = '$bot_token'" > "$CONFIG_FILE"
        echo "ADMIN_IDS = [$admin_ids]" >> "$CONFIG_FILE"
        echo "CHAT_ID = '$chat_id'" >> "$CONFIG_FILE"
        echo "✅ Система готова!"
    fi
}

show_menu() {
    clear
    echo "==============================="
    echo "    🤖 КЕРУВАННЯ POWER-BOT v2.2"
    echo "==============================="
    echo "1. Запустити бот (Захищений режим)"
    echo "2. Оновити бот (Git Pull)"
    echo "3. Ролбек (Повернути попередню версію)"
    echo "4. Скинути налаштування (Reset Config)"
    echo "5. Переглянути логи"
    echo "6. Вихід"
    echo "==============================="
}

# Запуск інсталятора перед меню
install_logic

while true; do
    show_menu
    read -p "Оберіть пункт [1-6]: " choice
    case $choice in
        1)
            echo "🚀 Запуск бота..."
            while true; do
                python "$BOT_FILE"
                
                # Перевірка на оновлення бота
                if [ -f ".update_bot" ]; then
                    cp "$BOT_FILE" "$BACKUP_FILE"
                    git fetch --all && git reset --hard origin/main
                    rm ".update_bot"
                    echo "✅ Бот оновлений."
                
                # Перевірка на відкат
                elif [ -f ".rollback_bot" ]; then
                    cp "$BACKUP_FILE" "$BOT_FILE"
                    rm ".rollback_bot"
                    echo "✅ Відкат виконано."

                # Перевірка на оновлення лаунчера
                elif [ -f ".update_launcher" ]; then
                    git checkout origin/main -- menu.sh
                    chmod +x menu.sh
                    rm ".update_launcher"
                    echo "✅ Лаунчер оновлено. Перезапустіть його."
                else
                    # Якщо маркерів немає, значить бот просто впав
                    echo "⚠️ Бот вимкнувся. Перезапуск через 5 сек..."
                    sleep 5
                fi
            done
            ;;
        2)
            echo "🌐 Оновлення з GitHub..."
            if [ -f "$BOT_FILE" ]; then
                cp "$BOT_FILE" "$BACKUP_FILE"
                echo "📦 Версію перед оновленням збережено."
            fi
            git fetch --all
            git reset --hard origin/main
            echo "✅ Оновлено до останньої версії GitHub."
            read -p "Натисніть Enter..."
            ;;
        3)
            echo "⏪ Відкат змін (Rollback)..."
            if [ -d ".git" ]; then
                git reset --hard HEAD@{1}
                echo "✅ Повернуто попередній стан коду."
            else
                echo "❌ Помилка: Репозиторій Git не знайдено."
            fi
            read -p "Натисніть Enter..."
            ;;
        4)
            read -p "⚠️ Видалити конфіг і налаштувати заново? (y/n): " confirm
            if [ "$confirm" == "y" ]; then
                rm "$CONFIG_FILE"
                echo "♻️ Налаштування скинуто. Перезапустіть Termux."
                exit 0
            fi
            ;;
        5)
            echo "--- Останні 20 рядків логів ---"
            tail -n 20 "$HOME/bot_log.txt" 2>/dev/null || echo "❌ Логи порожні."
            read -p "Натисніть Enter..."
            ;;
        6)
            echo "👋 До зустрічі!"
            exit 0
            ;;
        *)
            echo "❌ Невірний вибір!"
            sleep 1
            ;;
    esac
done
