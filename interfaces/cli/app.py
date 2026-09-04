"""
Интерактивный консольный интерфейс (TUI) для YouTubeDownload.

Использует:
- rich: для стильного оформления, рамок, таблиц и анимированных прогресс-баров.
- questionary: для удобного интерактивного выбора стрелками клавиатуры.
"""

import sys
from pathlib import Path
from typing import Optional

import questionary
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from core.config import config
from core.downloader import DownloadManager
from core.extractor import VideoInfo, extract_video_info
from utils.clipboard import get_youtube_url_from_clipboard, is_youtube_url
from utils.system import open_file, reveal_in_finder, send_macos_notification

console = Console()


def print_banner() -> None:
    """Выводит красивый приветственный баннер."""
    banner_text = (
        "[bold cyan]▶ YouTubeDownload[/bold cyan] [dim]v1.0[/dim]\n"
        "[white]Персональный загрузчик видео без рекламы, подписок и ограничений[/white]"
    )
    console.print(Panel(banner_text, border_style="cyan", expand=False))


def display_video_card(info: VideoInfo) -> None:
    """Отображает карточку с подробной информацией о видеоролике."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Ключ", style="bold cyan")
    table.add_column("Значение", style="white")

    table.add_row("Название:", f"[bold yellow]{info.title}[/bold yellow]")
    table.add_row("Автор / Канал:", info.channel)
    table.add_row("Длительность:", info.formatted_duration)
    if info.view_count:
        table.add_row("Просмотры:", f"{info.view_count:,}".replace(",", " "))
    table.add_row("Ссылка:", f"[dim]{info.webpage_url}[/dim]")

    panel = Panel(table, title="[bold green]Найдено видео[/bold green]", border_style="green")
    console.print(panel)


def ask_target_url(initial_url: Optional[str] = None) -> Optional[str]:
    """
    Запрашивает ссылку у пользователя.
    Если в буфере обмена есть ссылка на YouTube, предлагает ее автоматически.
    """
    if initial_url and is_youtube_url(initial_url):
        return initial_url.strip()

    # Проверяем буфер обмена
    cb_url = get_youtube_url_from_clipboard()
    if cb_url:
        use_clipboard = questionary.confirm(
            f"В буфере обмена найдена ссылка на YouTube:\n{cb_url}\nИспользовать её?",
            default=True,
            qmark="📋"
        ).ask()
        if use_clipboard:
            return cb_url

    # Если буфер пуст или пользователь отказался, вводим вручную
    while True:
        url = questionary.text(
            "Вставьте ссылку на YouTube (или нажмите Ctrl+C для выхода):",
            qmark="🔗"
        ).ask()

        if url is None:  # Нажат Ctrl+C / отмена
            return None

        url = url.strip()
        if not url:
            continue

        if is_youtube_url(url):
            return url
        else:
            rprint("[bold red]Ошибка:[/bold red] Введенная строка не похожа на ссылку YouTube. Попробуйте еще раз.")


def select_download_format(info: VideoInfo) -> Optional[dict]:
    """
    Предлагает интерактивное меню выбора качества на русском языке.
    """
    resolutions = info.get_available_resolutions()

    choices = []

    # Лучшее доступное видео
    choices.append(questionary.Choice(
        title="🌟 Лучшее доступное качество (Full HD / 4K со звуком)",
        value={"type": "video", "resolution": "best"}
    ))

    # Конкретные доступные разрешения
    for res in resolutions:
        label = f"{res}p"
        if res >= 2160:
            label += " (4K Ultra HD)"
        elif res >= 1440:
            label += " (2K Quad HD)"
        elif res == 1080:
            label += " (Full HD)"
        elif res == 720:
            label += " (HD)"

        choices.append(questionary.Choice(
            title=f"🎥 Видео: {label}",
            value={"type": "video", "resolution": f"{res}p"}
        ))

    # Аудио форматы
    choices.append(questionary.Separator())
    choices.append(questionary.Choice(
        title="🎵 Только звук: MP3 (Высокое качество, 320 kbps с обложкой)",
        value={"type": "audio", "format": "mp3"}
    ))
    choices.append(questionary.Choice(
        title="🎧 Только звук: M4A (Оригинальное аудио AAC без пережатия)",
        value={"type": "audio", "format": "m4a"}
    ))

    choices.append(questionary.Separator())
    choices.append(questionary.Choice(
        title="❌ Отмена",
        value=None
    ))

    selected = questionary.select(
        "Выберите формат для скачивания:",
        choices=choices,
        qmark="⚙️"
    ).ask()

    return selected


def run_download_with_progress(url: str, format_choice: dict) -> Optional[str]:
    """
    Запускает скачивание с отображением анимированного прогресс-бара Rich.
    """
    is_audio = format_choice.get("type") == "audio"
    resolution = format_choice.get("resolution", "1080p")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        BarColumn(bar_width=40, complete_style="green", finished_style="bold green"),
        TextColumn("[bold green]{task.percentage:>3.0f}%[/bold green]"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:

        task_id: TaskID = progress.add_task("Подготовка к скачиванию...", total=100)

        def on_progress(data: dict) -> None:
            status = data.get("status")
            if status == "downloading":
                percent = data.get("percent", 0.0)
                progress.update(
                    task_id,
                    completed=percent,
                    description=f"Скачивание ({data.get('speed_str', '')})"
                )
            elif status == "processing":
                progress.update(
                    task_id,
                    completed=100,
                    description="[yellow]Склейка потоков через FFmpeg...[/yellow]"
                )
            elif status == "finished":
                progress.update(
                    task_id,
                    completed=100,
                    description="[bold green]Завершено![/bold green]"
                )

        manager = DownloadManager(progress_callback=on_progress)

        try:
            downloaded_path = manager.download(
                url=url,
                resolution=resolution,
                audio_only=is_audio,
                output_dir=config.download_path
            )
            return downloaded_path
        except Exception as e:
            console.print(f"[bold red]Ошибка во время загрузки:[/bold red] {e}")
            return None


def run_cli_app(initial_url: Optional[str] = None) -> None:
    """
    Основной цикл консольного приложения.
    """
    print_banner()

    target_url = initial_url

    while True:
        try:
            # 1. Получение URL
            url = ask_target_url(target_url)
            # Сбрасываем переданный аргумент после первого использования
            target_url = None

            if not url:
                rprint("[yellow]Работа завершена.[/yellow]")
                break

            # 2. Получение метаданных ролика
            with console.status("[bold cyan]Получение информации о видео с YouTube...[/bold cyan]", spinner="dots"):
                try:
                    info = extract_video_info(url)
                except Exception as e:
                    rprint(f"[bold red]Не удалось проанализировать ссылку:[/bold red] {e}")
                    if questionary.confirm("Попробовать другую ссылку?", default=True).ask():
                        continue
                    break

            # 3. Карточка ролика
            display_video_card(info)

            # 4. Выбор качества
            format_choice = select_download_format(info)
            if not format_choice:
                rprint("[yellow]Загрузка отменена.[/yellow]")
                if not questionary.confirm("Скачать другое видео?", default=True).ask():
                    break
                continue

            # 5. Загрузка
            rprint(f"\n[cyan]Папка сохранения:[/cyan] [dim]{config.download_path}[/dim]\n")
            result_path = run_download_with_progress(url, format_choice)

            if result_path and Path(result_path).exists():
                file_size_mb = Path(result_path).stat().st_size / (1024 * 1024)
                success_text = (
                    f"[bold green]✔ Файл успешно скачан![/bold green]\n"
                    f"[white]Путь:[/white] [cyan]{result_path}[/cyan]\n"
                    f"[white]Размер:[/white] {file_size_mb:.1f} МБ"
                )
                console.print(Panel(success_text, border_style="green"))

                # Нативное уведомление macOS
                send_macos_notification(
                    title="YouTubeDownload",
                    message="Видео успешно загружено и готово!",
                    subtitle=info.title[:40]
                )

                # Меню дальнейших действий
                next_action = questionary.select(
                    "Что сделать дальше?",
                    choices=[
                        questionary.Choice("📂 Показать файл в Finder", value="finder"),
                        questionary.Choice("▶️ Открыть и воспроизвести", value="play"),
                        questionary.Choice("📥 Скачать еще одно видео", value="again"),
                        questionary.Choice("🚪 Завершить работу", value="exit"),
                    ],
                    qmark="👉"
                ).ask()

                if next_action == "finder":
                    reveal_in_finder(result_path)
                elif next_action == "play":
                    open_file(result_path)

                if next_action != "again":
                    rprint("[cyan]Спасибо за использование YouTubeDownload![/cyan]")
                    break
            else:
                rprint("[bold red]Файл не был сохранен или произошла ошибка.[/bold red]")
                if not questionary.confirm("Попробовать снова?", default=True).ask():
                    break

        except KeyboardInterrupt:
            rprint("\n[yellow]Прервано пользователем. Выход.[/yellow]")
            break
        except Exception as e:
            rprint(f"[bold red]Непредвиденная ошибка:[/bold red] {e}")
            break
