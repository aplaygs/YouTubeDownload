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
import sysconfig
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFilter

# Базовая директория проекта
PROJECT_DIR = Path(__file__).resolve().parent
APPLICATIONS_DIR = Path("/Applications")
APP_BUNDLE_PATH = APPLICATIONS_DIR / "YouTubeDownload.app"


def generate_app_icon(output_icns: Path) -> bool:
    """
    Генерирует премиальную иконку приложения в стиле Android 17 Material You Dark:
    - Глубокий темный графитовый squircle (#121316 -> #202229) с мягкой внешней тенью и тонким кантом
    - Парящий центральный дисплей YouTube в насыщенном градиенте (#FF304F -> #B80A22) со стеклянным бликом
    - Центрированный белый символ воспроизведения со скругленными вершинами и деликатной тенью
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
    s_draw.rounded_rectangle([margin, margin + 28, size - margin, size - margin + 28], radius=radius, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(38))

    # 2. Темный корпус Squircle (#24262E -> #101115)
    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(box, radius=radius, fill=255)

    dark_grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dg_draw = ImageDraw.Draw(dark_grad)
    for y in range(margin, size - margin):
        t = (y - margin) / (size - 2 * margin)
        val = int(36 * (1 - t) + 16 * t)
        dg_draw.line([(margin, y), (size - margin, y)], fill=(val, val + 2, val + 5, 255))

    body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    body.paste(dark_grad, (0, 0), mask)

    # Металлическая кромка по контуру
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r_draw = ImageDraw.Draw(rim)
    r_draw.rounded_rectangle([margin + 1, margin + 1, size - margin - 1, size - margin - 1], radius=radius - 1, outline=(255, 255, 255, 55), width=2)
    r_draw.rounded_rectangle([margin + 2, margin + 3, size - margin - 2, size - margin], radius=radius - 2, outline=(0, 0, 0, 95), width=3)
    body = Image.alpha_composite(body, Image.composite(rim, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    # 3. Центральный дисплей YouTube Screen (4x суперсемплинг)
    scale = 4
    hi_sz = size * scale
    p_w, p_h = 2460, 1720
    p_cx, p_cy = 2048, 2048

    plate_mask = Image.new("L", (hi_sz, hi_sz), 0)
    pm_draw = ImageDraw.Draw(plate_mask)
    pm_draw.rounded_rectangle([p_cx - p_w // 2, p_cy - p_h // 2, p_cx + p_w // 2, p_cy + p_h // 2], radius=520, fill=255)

    hi_plate = Image.new("RGBA", (hi_sz, hi_sz), (0, 0, 0, 0))
    hp_draw = ImageDraw.Draw(hi_plate)
    for y in range(p_cy - p_h // 2, p_cy + p_h // 2):
        t = (y - (p_cy - p_h // 2)) / p_h
        t = t * t * (3 - 2 * t)
        r = int(255 * (1 - t) + 170 * t)
        g = int(48 * (1 - t) + 10 * t)
        b = int(72 * (1 - t) + 24 * t)
        hp_draw.line([(0, y), (hi_sz, y)], fill=(r, g, b, 255))

    # Стеклянный градиентный блик сверху
    glass_layer = Image.new("RGBA", (hi_sz, hi_sz), (0, 0, 0, 0))
    gl_draw = ImageDraw.Draw(glass_layer)
    for y in range(p_cy - p_h // 2, p_cy - p_h // 2 + 600):
        t = (y - (p_cy - p_h // 2)) / 600.0
        alpha = int(45 * (1 - t))
        gl_draw.line([(0, y), (hi_sz, y)], fill=(255, 255, 255, alpha))

    hi_plate = Image.alpha_composite(hi_plate, glass_layer)

    plate_final = Image.new("RGBA", (hi_sz, hi_sz), (0, 0, 0, 0))
    plate_final.paste(hi_plate, (0, 0), plate_mask)

    # 4. Центрированный символ Play с мягким скруглением углов
    sym_mask = Image.new("L", (hi_sz, hi_sz), 0)
    sm_draw = ImageDraw.Draw(sym_mask)

    tri_r = 540
    t_cx, t_cy = 2048 + 60, 2048
    v1 = (t_cx + tri_r, t_cy)
    v2 = (t_cx - tri_r * 0.5, t_cy + tri_r * math.sqrt(3) / 2)
    v3 = (t_cx - tri_r * 0.5, t_cy - tri_r * math.sqrt(3) / 2)
    sm_draw.polygon([v1, v2, v3], fill=255)

    blurred_sym = sym_mask.filter(ImageFilter.GaussianBlur(32))
    rounded_sym = blurred_sym.point(lambda p: 255 if p > 128 else 0)

    sym_img = Image.new("RGBA", (hi_sz, hi_sz), (0, 0, 0, 0))
    si_draw = ImageDraw.Draw(sym_img)
    for y in range(int(t_cy - tri_r), int(t_cy + tri_r)):
        t = (y - (t_cy - tri_r)) / (2 * tri_r)
        val = int(255 * (1 - t) + 242 * t)
        si_draw.line([(0, y), (hi_sz, y)], fill=(val, val, val, 255))

    plate_final.paste(sym_img, (0, 0), rounded_sym)

    plate_1024 = plate_final.resize((size, size), Image.Resampling.LANCZOS)
    plate_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    plate_shadow.paste((0, 0, 0, 140), (0, 20), plate_1024.split()[3])
    plate_shadow = plate_shadow.filter(ImageFilter.GaussianBlur(26))

    final_icon = Image.alpha_composite(shadow, body)
    final_icon = Image.alpha_composite(final_icon, plate_shadow)
    final_icon = Image.alpha_composite(final_icon, plate_1024)

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

    # 3. Компиляция нативного Mach-O лаунчера (Cocoa + Python C API)
    # Гарантирует правильную регистрацию бандла в macOS:
    # Иконка AppIcon отображается в Dock, имя процесса и меню — YouTubeDownload (а не Python).
    executable_path = macos_dir / "YouTubeDownload"

    inc_dir = sysconfig.get_path("include")
    lib_dir = sysconfig.get_config_var("LIBDIR")
    py_ver = sysconfig.get_config_var("VERSION")

    launcher_src = f"""#import <Cocoa/Cocoa.h>
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {{
    // Не вызываем [NSApplication sharedApplication] здесь:
    // Tkinter (libtk8.6) использует собственный подкласс TKApplication.
    // Преждевременный вызов NSApplication ломает селектор macOSVersion в Tk.
    const char *project_dir = "{PROJECT_DIR}";
    char python_path[4096];
    snprintf(python_path, sizeof(python_path), "%s:%s/venv/lib/python3.12/site-packages", project_dir, project_dir);
    setenv("PYTHONPATH", python_path, 1);

    const char *cur_path = getenv("PATH");
    char new_path[4096];
    snprintf(new_path, sizeof(new_path), "%s/venv/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:%s", project_dir, cur_path ? cur_path : "");
    setenv("PATH", new_path, 1);

    char script_path[4096];
    snprintf(script_path, sizeof(script_path), "%s/main.py", project_dir);

    int py_argc = 2;
    char *py_argv[32];
    py_argv[0] = argv[0];
    py_argv[1] = script_path;

    for (int i = 1; i < argc && py_argc < 30; i++) {{
        if (strncmp(argv[i], "-psn_", 5) != 0) {{
            py_argv[py_argc++] = argv[i];
        }}
    }}
    py_argv[py_argc++] = "--gui";
    py_argv[py_argc] = NULL;

    return Py_BytesMain(py_argc, py_argv);
}}
"""
    cache_dir = PROJECT_DIR / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    launcher_m = cache_dir / "launcher.m"
    with open(launcher_m, "w", encoding="utf-8") as f:
        f.write(launcher_src)

    compiled = False
    try:
        cmd = [
            "clang", "-arch", "arm64", "-framework", "Cocoa",
            f"-I{inc_dir}",
            f"-L{lib_dir}", f"-lpython{py_ver}",
            f"-Wl,-rpath,{lib_dir}",
            "-o", str(executable_path),
            str(launcher_m)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            compiled = True
        else:
            print(f"[Предупреждение] Ошибка компиляции лаунчера: {res.stderr}")
    except Exception as e:
        print(f"[Предупреждение] Ошибка вызова clang: {e}")

    if not compiled:
        # Резервный bash-лаунчер
        launcher_script = f"""#!/bin/bash
DIR="{PROJECT_DIR}"
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
exec /usr/bin/arch -arm64 "$DIR/venv/bin/python" "$DIR/main.py" --gui
"""
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
