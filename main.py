"""
Главная точка входа в программу YouTubeDownload.

Поддерживает:
1. Интерактивный терминальный режим: `python main.py --cli`
2. Графический интерфейс: `python main.py --gui`
3. Прямую загрузку по ссылке: `python main.py "https://youtube.com/watch?v=..."`
4. Автоматическое определение режима при обычном запуске: `python main.py`
"""

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTubeDownload — Быстрый персональный загрузчик видео с YouTube"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="Ссылка на YouTube-видео для скачивания"
    )
    parser.add_argument(
        "--cli", "-c",
        action="store_true",
        help="Принудительный запуск терминального интерактивного интерфейса"
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="Принудительный запуск графического окна (CustomTkinter)"
    )
    parser.add_argument(
        "--res", "-r",
        default="1080p",
        help="Разрешение видео (например: 1080p, 720p, 4k, best)"
    )
    parser.add_argument(
        "--audio", "-a",
        action="store_true",
        help="Скачать только аудио в MP3 (320 kbps)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Пользовательская папка для сохранения"
    )

    # Фильтруем системные флаги macOS LaunchServices (например, -psn_0_xxxxx)
    filtered_argv = [a for a in sys.argv[1:] if not a.startswith("-psn_")]
    args, _ = parser.parse_known_args(filtered_argv)

    # 1. Если передана ссылка напрямую с флагами без интерактивности
    if args.url and not args.gui and not args.cli:
        from core.config import config
        from core.downloader import DownloadManager
        from utils.system import reveal_in_finder, send_macos_notification

        print(f"🎬 Начало загрузки: {args.url}")
        target_dir = Path(args.output).resolve() if args.output else config.download_path

        def cli_progress(data: dict):
            status = data.get("status")
            if status == "downloading":
                pct = data.get("percent", 0.0)
                spd = data.get("speed_str", "")
                eta = data.get("eta_str", "")
                sys.stdout.write(f"\rСкачивание: {pct:.1f}% [{spd}, ETA {eta}]   ")
                sys.stdout.flush()
            elif status == "processing":
                sys.stdout.write("\rСклейка потоков через FFmpeg...                     \n")
                sys.stdout.flush()

        manager = DownloadManager(progress_callback=cli_progress)
        try:
            res_path = manager.download(
                url=args.url,
                resolution=args.res,
                audio_only=args.audio,
                output_dir=target_dir
            )
            print(f"\n✔ Видео успешно сохранено:\n{res_path}")
            send_macos_notification("YouTubeDownload", "Загрузка завершена!", os.path.basename(res_path))
            reveal_in_finder(res_path)
            return
        except Exception as e:
            print(f"\n❌ Ошибка загрузки: {e}", file=sys.stderr)
            sys.exit(1)

    # 2. Если запрошен интерфейс CLI
    if args.cli:
        from interfaces.cli.app import run_cli_app
        run_cli_app(initial_url=args.url)
        return

    # 3. Если запрошен интерфейс GUI
    if args.gui:
        from interfaces.gui.window import run_gui_app
        run_gui_app(initial_url=args.url)
        return

    # 4. Режим по умолчанию:
    # Если запущен из интерактивного терминала — запускаем удобный TUI,
    # если запущен кликом мыши (Finder/Spotlight) — открываем GUI.
    if sys.stdin.isatty():
        from interfaces.cli.app import run_cli_app
        run_cli_app(initial_url=args.url)
    else:
        from interfaces.gui.window import run_gui_app
        run_gui_app(initial_url=args.url)


if __name__ == "__main__":
    main()
