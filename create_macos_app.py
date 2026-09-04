"""
Скрипт создания нативного приложения macOS (.app) для YouTubeDownload.

Создает:
1. Иконку приложения в стиле macOS (AppIcon.icns).
2. Пакет /Applications/YouTubeDownload.app (отображается в Launchpad, Finder и Spotlight).
3. Исполняемый файл запуска GUI.
4. Регистрирует приложение в Launch Services macOS.
"""

import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

# Базовая директория проекта
PROJECT_DIR = Path(__file__).resolve().parent
APPLICATIONS_DIR = Path("/Applications")
APP_BUNDLE_PATH = APPLICATIONS_DIR / "YouTubeDownload.app"


def generate_app_icon(output_icns: Path) -> bool:
    """
    Генерирует иконку приложения macOS в формате .icns:
    Красный закругленный квадрат (squircle) с белым треугольником воспроизведения YouTube.
    """
    temp_iconset_dir = PROJECT_DIR / "AppIcon.iconset"
    temp_iconset_dir.mkdir(parents=True, exist_ok=True)

    # Размеры для иконок macOS
    sizes = [16, 32, 64, 128, 256, 512, 1024]

    # Базовое изображение 1024x1024
    base_size = 1024
    img = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Параметры macOS squircle (скругленный квадрат)
    margin = 80
    corner_radius = 210
    box = [margin, margin, base_size - margin, base_size - margin]

    # Основной красный фон YouTube (#FF0000 -> #CC0000 градиент/сплошной)
    draw.rounded_rectangle(box, radius=corner_radius, fill="#E62117")

    # Внутренний треугольник Play (белый)
    # Координаты треугольника: направлен вправо
    tri_left = 410
    tri_right = 690
    tri_top = 370
    tri_bottom = 654
    center_y = (tri_top + tri_bottom) // 2

    triangle = [
        (tri_left, tri_top),
        (tri_right, center_y),
        (tri_left, tri_bottom)
    ]
    draw.polygon(triangle, fill="#FFFFFF")

    # Генерируем все необходимые размеры для iconset
    iconset_mappings = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    for filename, sz in iconset_mappings:
        resized = img.resize((sz, sz), Image.Resampling.LANCZOS)
        resized.save(temp_iconset_dir / filename, "PNG")

    # Конвертируем через системную утилиту iconutil
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(temp_iconset_dir), "-o", str(output_icns)],
            check=True,
            capture_output=True
        )
        shutil.rmtree(temp_iconset_dir, ignore_errors=True)
        return True
    except Exception as e:
        print(f"[Ошибка создания icns] {e}")
        shutil.rmtree(temp_iconset_dir, ignore_errors=True)
        return False


def build_macos_app_bundle() -> Path:
    """Создает структуру /Applications/YouTubeDownload.app."""
    contents_dir = APP_BUNDLE_PATH / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    # 1. Генерация иконки
    icon_path = resources_dir / "AppIcon.icns"
    generate_app_icon(icon_path)

    # 2. Создание Info.plist
    info_plist_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>YouTubeDownload</string>
    <key>CFBundleDisplayName</key>
    <string>YouTubeDownload</string>
    <key>CFBundleIdentifier</key>
    <string>com.aplaygs.youtubedownload</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>YouTubeDownload</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
</dict>
</plist>
"""
    with open(contents_dir / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist_content)

    # 3. Создание скрипта запуска в MacOS/YouTubeDownload
    launcher_script = f"""#!/bin/bash
DIR="{PROJECT_DIR}"
exec "$DIR/venv/bin/python" "$DIR/main.py" --gui
"""
    executable_path = macos_dir / "YouTubeDownload"
    with open(executable_path, "w", encoding="utf-8") as f:
        f.write(launcher_script)

    executable_path.chmod(0o755)

    # 4. Обновление базы данных Launch Services macOS, чтобы иконка появилась в Launchpad и Spotlight
    lsregister = "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    if os.path.exists(lsregister):
        try:
            subprocess.run([lsregister, "-f", str(APP_BUNDLE_PATH)], check=True, capture_output=True)
            # Принудительно перезагружаем Finder и Dock для обновления Launchpad
            subprocess.run(["killall", "Dock"], capture_output=True)
        except Exception:
            pass

    print(f"✔ Приложение успешно создано: {APP_BUNDLE_PATH}")
    return APP_BUNDLE_PATH


if __name__ == "__main__":
    build_macos_app_bundle()
