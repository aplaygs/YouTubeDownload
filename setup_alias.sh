#!/usr/bin/env bash
# ==============================================================================
# Скрипт добавления псевдонима 'ytdl' в ~/.zshrc для запуска из любого каталога
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ZSHRC="$HOME/.zshrc"
ALIAS_CMD="alias ytdl=\"$DIR/run.sh\""

# Создаем .zshrc, если он не существует
touch "$ZSHRC"

# Проверяем, добавлен ли уже алиас
if grep -Fq "alias ytdl=" "$ZSHRC"; then
    echo "✔ Псевдоним 'ytdl' уже присутствует в $ZSHRC"
else
    echo "" >> "$ZSHRC"
    echo "# YouTubeDownload shortcut" >> "$ZSHRC"
    echo "$ALIAS_CMD" >> "$ZSHRC"
    echo "✔ Псевдоним 'ytdl' успешно добавлен в $ZSHRC"
    echo "Для применения выполните: source ~/.zshrc или перезапустите терминал."
fi
