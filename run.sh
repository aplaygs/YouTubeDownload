#!/usr/bin/env bash
# ==============================================================================
# YouTubeDownload — Скрипт быстрого запуска для macOS
# ==============================================================================

set -e

# Определение директории проекта независимо от того, откуда вызван скрипт
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Проверка наличия виртуального окружения
if [ ! -d "$DIR/venv" ]; then
    echo "Создание виртуального окружения Python..."
    python3 -m venv "$DIR/venv"
    "$DIR/venv/bin/pip" install --upgrade pip
    "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt"
fi

# Запуск программы через виртуальное окружение с передачей всех аргументов
exec "$DIR/venv/bin/python" "$DIR/main.py" "$@"
