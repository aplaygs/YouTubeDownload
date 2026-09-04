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
import math
from PIL import Image, ImageDraw, ImageFilter

# Базовая директория проекта
PROJECT_DIR = Path(__file__).resolve().parent
APPLICATIONS_DIR = Path("/Applications")
APP_BUNDLE_PATH = APPLICATIONS_DIR / "YouTubeDownload.app"


def generate_app_icon(output_icns: Path) -> bool:
    """
    Генерирует стильную премиальную иконку macOS в формате .icns:
    - Apple squircle с градиентом #FF2647 -> #940018
    - Внутреннее радиальное свечение и верхний стеклянный блик (glass specular highlight)
    - Тонкая металлическая кромка по контуру
    - Мягкая нижняя тень для эффекта парения в Dock
    - Центральный символ воспроизведения с закругленными углами и деликатной тенью
    """
    temp_iconset_dir = PROJECT_DIR / "AppIcon.iconset"
    temp_iconset_dir.mkdir(parents=True, exist_ok=True)

    size = 1024
    margin = 82
    radius = 224
    box = [margin, margin, size - margin, size - margin]

    # 1. Мягкая внешняя тень иконки
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle([margin, margin + 30, size - margin, size - margin + 30], radius=radius, fill=(0, 0, 0, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(38))

    # 2. Маска squircle
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(box, radius=radius, fill=255)

    # 3. Насыщенный градиент с радиальной подсветкой сверху-по-центру
    base_grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(base_grad)

    for y in range(margin, size - margin):
        for x in range(margin, size - margin):
            dx = (x - 512) / 450.0
            dy = (y - 340) / 450.0
            dist = min(1.0, math.sqrt(dx * dx + dy * dy))
            vy = (y - margin) / (size - 2 * margin)
            t = vy * 0.62 + dist * 0.38
            t = t * t * (3 - 2 * t)
            r = int(255 * (1 - t) + 148 * t)
            g = int(48 * (1 - t) + 4 * t)
            b = int(72 * (1 - t) + 18 * t)
            bg_draw.point((x, y), fill=(r, g, b, 255))

    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    body.paste(base_grad, (0, 0), mask)

    # 4. Верхний стеклянный блик
    glass = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glass)
    for y in range(margin, margin + 260):
        alpha = int(45 * (1 - (y - margin) / 260))
        g_draw.line([(margin, y), (size - margin, y)], fill=(255, 255, 255, alpha))
    body = Image.alpha_composite(body, Image.composite(glass, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    # 5. Тонкая кромка по краю
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(rim)
    r_draw.rounded_rectangle([margin + 1, margin + 1, size - margin - 1, size - margin - 1], radius=radius - 1, outline=(255, 255, 255, 115), width=3)
    r_draw.rounded_rectangle([margin + 2, margin + 4, size - margin - 2, size - margin], radius=radius - 2, outline=(0, 0, 0, 80), width=2)
    body = Image.alpha_composite(body, Image.composite(rim, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    # 6. Символ Play с мягким скруглением углов (4x суперсемплинг)
    scale = 4
    hi_size = size * scale
    sym_mask = Image.new("L", (hi_size, hi_size), 0)
    sm_draw = ImageDraw.Draw(sym_mask)

    cx = 2048 + 80
    cy = 2048
    r_tri = 740

    v1 = (cx + r_tri, cy)
    v2 = (cx - r_tri * 0.5, cy + r_tri * math.sqrt(3) / 2)
    v3 = (cx - r_tri * 0.5, cy - r_tri * math.sqrt(3) / 2)
    sm_draw.polygon([v1, v2, v3], fill=255)

    blurred_sym = sym_mask.filter(ImageFilter.GaussianBlur(36))
    rounded_sym = blurred_sym.point(lambda p: 255 if p > 128 else 0)

    sym_col = Image.new("RGBA", (hi_size, hi_size), (0, 0, 0, 0))
    sc_draw = ImageDraw.Draw(sym_col)
    for y in range(int(cy - r_tri), int(cy + r_tri)):
        if 0 <= y < hi_size:
            t = (y - (cy - r_tri)) / (2 * r_tri)
            val = int(255 * (1 - t) + 242 * t)
            sc_draw.line([(0, y), (hi_size, y)], fill=(val, val, val, 255))

    final_hi_sym = Image.new("RGBA", (hi_size, hi_size), (0, 0, 0, 0))
    final_hi_sym.paste(sym_col, (0, 0), rounded_sym)

    sym_1024 = final_hi_sym.resize((size, size), Image.Resampling.LANCZOS)

    # 7. Тень под символом воспроизведения
    sym_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sym_shadow.paste((0, 0, 0, 110), (0, 18), sym_1024.split()[3])
    sym_shadow = sym_shadow.filter(ImageFilter.GaussianBlur(16))

    # Сборка итогового изображения 1024x1024
    final_icon = Image.alpha_composite(shadow, body)
    final_icon = Image.alpha_composite(final_icon, sym_shadow)
    final_icon = Image.alpha_composite(final_icon, sym_1024)

    # Сохраняем все размеры для iconset macOS
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
        resized = final_icon.resize((sz, sz), Image.Resampling.LANCZOS)
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

    # 2. Создание Info.plist с явным указанием архитектуры arm64 (без Rosetta 2)
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
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
    </array>
    <key>LSRequiresNativeExecution</key>
    <true/>
</dict>
</plist>
"""
    with open(contents_dir / "Info.plist", "w", encoding="utf-8") as f:
        f.write(info_plist_content)

    # 3. Создание скрипта запуска в MacOS/YouTubeDownload (строго native arm64)
    launcher_script = f"""#!/bin/bash
DIR="{PROJECT_DIR}"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
exec /usr/bin/arch -arm64 "$DIR/venv/bin/python" "$DIR/main.py" --gui
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
