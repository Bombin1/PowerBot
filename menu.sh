#!/data/data/com.termux/files/usr/bin/bash

# Шлях до файлів
BOT_FILE="$HOME/light_bot.py"
chmod +x "$HOME/menu.sh" 2>/dev/null
BACKUP_FILE="$HOME/light_bot_backup.py"
CONFIG_FILE="$HOME/config.py"
# Для релізів нам потрібна назва репозиторію у форматі Юзер/Репо
REPO="Bombin1/PowerBot"

# --- [ БЛОК ІНСТАЛЯЦІЇ ТА АВТОЗАПУСКУ ] ---
install_logic() {
    if ! grep -q "menu.sh" ~/.bashrc; then
        echo "⚙️ Налаштування автозапуску при старті Termux..."
        echo "if [ -f ~/menu.sh ]; then ./menu.sh; fi" >> ~/.bashrc
    fi

    if [ ! -f "$CONFIG_FILE" ]; then
        echo "🆕 Перший запуск. Налаштування системи..."
        pkg update && pkg upgrade -y
        pkg install python requests curl unzip termux-api -y
        pip install pyTelegramBotAPI requests
        termux-wake-lock
        
        # Завантажуємо останній стабільний реліз замість git clone
        echo "📥 Завантаження останньої версії бота..."
        ZIP_URL=$(curl -s https://api.github.com/repos/$REPO/releases/latest | grep "zipball_url" | cut -d '"' -f 4)
        curl -L "$ZIP_URL" -o initial.zip
        unzip -q initial.zip -d temp_install
        mv temp_install/*/* .
        rm -rf temp_install initial.zip

        echo "--- Налаштування конфігурації ---"
        read -p "Введіть TOKEN бота: " bot_token
        read -p "Введіть ID Адмінів (напр: 123,456): " admin_ids
        read -p "Введіть ID Групи/Каналу (з мінусом): " chat_id

        echo "BOT_TOKEN = '$bot_token'" > "$CONFIG_FILE"
        echo "ADMIN_IDS = [$admin_ids]" >> "$CONFIG_FILE"
        echo "CHAT_ID = '$chat_id'" >> "$CONFIG_FILE"
        echo "✅ Система готова!"
    fi
}

# --- [ ЛОГІКА БЕЗПЕЧНОГО ОНОВЛЕННЯ ] ---
perform_update() {
    local zip_path=".update_url"
    if [ -f "$zip_path" ]; then
        URL=$(cat "$zip_path")
    else
        URL=$(curl -s https://api.github.com/repos/$REPO/releases/latest | grep "zipball_url" | cut -d '"' -f 4)
    fi

    if [ ! -z "$URL" ]; then
        echo "📥 Завантаження архіву оновлення..."
        cp "$BOT_FILE" "$BACKUP_FILE" 2>/dev/null
        curl -L "$URL" -o update.zip
        
        echo "📦 Розпакування (конфіги захищено)..."
        mkdir -p temp_update
        unzip -q update.zip -d temp_update
        
        # Копіюємо все КРІМ конфігів та бази даних
        find temp_update/*/* -maxdepth 0 -not -name 'config.py' -not -name 'user_settings.json' -not -name 'database.db' -exec cp -rf {} . \;
        
        # --- [ ОСЬ ЦЕЙ ВАЖЛИВИЙ МОМЕНТ ] ---
        chmod +x "$HOME/menu.sh"
        # ----------------------------------

        rm -rf temp_update update.zip .update_url .update_bot
        echo "✅ Оновлення завершено! Права на menu.sh поновлено."
    else
        echo "❌ Помилка: Не вдалося отримати посилання на реліз."
    fi
}

show_menu() {
    clear
    echo "==============================="
    echo "    🤖 КЕРУВАННЯ POWER-BOT"
    echo "==============================="
    echo "1. Запустити бот (Авторестарт)"
    echo "2. Оновити бот (GitHub Release)"
    echo "3. Ролбек (Повернути backup.py)"
    echo "4. Скинути конфіг (Reset)"
    echo "5. Переглянути логи"
    echo "6. Вихід"
    echo "==============================="
}

install_logic

while true; do
    show_menu
    read -p "Оберіть пункт [1-6]: " choice
    case $choice in
        1)
            echo "🚀 Запуск бота..."
            while true; do
                python "$BOT_FILE"
                
                # Перевірка на запит оновлення від самого бота
                if [ -f ".update_bot" ]; then
                    perform_update
                
                # Перевірка на відкат
                elif [ -f ".rollback_bot" ]; then
                    if [ -f "$BACKUP_FILE" ]; then
                        cp "$BACKUP_FILE" "$BOT_FILE"
                        echo "✅ Відкат виконано."
                    else
                        echo "❌ Бекап не знайдено!"
                    fi
                    rm ".rollback_bot"

                else
                    echo "⚠️ Бот зупинився. Перезапуск через 5 сек..."
                    sleep 5
                fi
            done
            ;;
        2)
            echo "🌐 Перевірка релізів..."
            perform_update
            read -p "Натисніть Enter..."
            ;;
        3)
            echo "⏪ Відкат до бекапу..."
            if [ -f "$BACKUP_FILE" ]; then
                cp "$BACKUP_FILE" "$BOT_FILE"
                echo "✅ Файл light_bot.py відновлено з бекапу."
            else
                echo "❌ Файл бекапу не знайдено."
            fi
            read -p "Натисніть Enter..."
            ;;
        4)
            read -p "⚠️ Скинути налаштування? (y/n): " confirm
            if [ "$confirm" == "y" ]; then
                rm "$CONFIG_FILE"
                echo "♻️ Конфіг видалено. Перезапустіть скрипт."
                exit 0
            fi
            ;;
        5)
            echo "--- Логи (останні 20 рядків) ---"
            tail -n 20 "$HOME/bot_log.txt" 2>/dev/null || echo "Логи порожні."
            read -p "Натисніть Enter..."
            ;;
        6)
            exit 0
            ;;
    esac
done
