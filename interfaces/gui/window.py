"""
Графический интерфейс пользователя (GUI) на CustomTkinter для macOS.

Особенности:
- Темная тема в стиле macOS.
- Предварительный просмотр обложки и информации о ролике.
- Потокобезопасная фоновая загрузка без зависания интерфейса.
- Индикатор прогресса, скорости и расчетного времени окончания.
- Интеграция с буфером обмена и системными уведомлениями macOS.
"""

import io
import os
import threading
from pathlib import Path
from typing import Callable, Optional
from urllib.request import Request, urlopen

import customtkinter as ctk
from PIL import Image

from core.config import config
from core.downloader import DownloadManager
from core.extractor import VideoInfo, extract_video_info
from utils.clipboard import get_clipboard_text, is_youtube_url
from utils.system import open_file, reveal_in_finder, send_macos_notification
from utils.vpn import is_vpn_active

# Настройка внешнего вида CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class YouTubeDownloadApp(ctk.CTk):
    """Главное окно приложения YouTubeDownload."""

    def __init__(self, initial_url: Optional[str] = None):
        super().__init__()

        self.title("YouTubeDownload — Загрузчик видео")
        self.geometry("780x680")
        self.minsize(700, 600)

        self.current_video_info: Optional[VideoInfo] = None
        self.download_manager: Optional[DownloadManager] = None
        self.last_downloaded_path: Optional[str] = None

        self._setup_ui()

        # Если передана начальная ссылка, вставляем и сразу анализируем
        if initial_url:
            self.url_entry.insert(0, initial_url)
            self._start_fetch_info()
        else:
            # Проверяем буфер обмена
            clip_text = get_clipboard_text()
            if is_youtube_url(clip_text):
                self.url_entry.insert(0, clip_text)
                self.status_label.configure(text="Ссылка обнаружена в буфере обмена. Нажмите «Найти видео».")

    def _setup_ui(self) -> None:
        """Инициализирует все элементы интерфейса."""
        # 1. Верхний заголовок
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(15, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="▶ YouTubeDownload",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(side="left")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Быстро, бесплатно и без рекламы",
            font=ctk.CTkFont(size=13),
            text_color="gray"
        )
        subtitle_label.pack(side="left", padx=(10, 0), pady=(4, 0))

        # Индикатор статуса VPN
        self.vpn_badge = ctk.CTkLabel(
            header_frame,
            text="Проверка VPN...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray"
        )
        self.vpn_badge.pack(side="right", padx=(0, 5))
        self._update_vpn_badge()

        # 2. Секция ввода URL
        url_frame = ctk.CTkFrame(self)
        url_frame.pack(fill="x", padx=20, pady=10)

        self.url_entry = ctk.CTkEntry(
            url_frame,
            placeholder_text="Вставьте ссылку на YouTube (https://www.youtube.com/watch?v=...)",
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=10)
        self.url_entry.bind("<Return>", lambda e: self._start_fetch_info())

        paste_btn = ctk.CTkButton(
            url_frame,
            text="📋 Вставить",
            width=90,
            height=38,
            command=self._on_paste_click
        )
        paste_btn.pack(side="left", padx=(0, 8), pady=10)

        self.search_btn = ctk.CTkButton(
            url_frame,
            text="🔍 Найти",
            width=90,
            height=38,
            fg_color="#1f538d",
            command=self._start_fetch_info
        )
        self.search_btn.pack(side="left", padx=(0, 10), pady=10)

        # 3. Карточка видео (превью + инфо)
        self.card_frame = ctk.CTkFrame(self)
        self.card_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # Контейнер для превью слева
        self.thumb_label = ctk.CTkLabel(
            self.card_frame,
            text="[ Нет превью ]",
            width=240,
            height=135,
            fg_color="#1a1a1a",
            corner_radius=8
        )
        self.thumb_label.pack(side="left", padx=15, pady=15, anchor="n")

        # Контейнер для метаданных справа
        self.meta_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.meta_frame.pack(side="left", fill="both", expand=True, padx=(0, 15), pady=15)

        self.video_title_label = ctk.CTkLabel(
            self.meta_frame,
            text="Вставьте ссылку и нажмите «Найти» для анализа видео",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
            wraplength=440,
            justify="left"
        )
        self.video_title_label.pack(fill="x", pady=(0, 5))

        self.video_channel_label = ctk.CTkLabel(
            self.meta_frame,
            text="Канал: —",
            font=ctk.CTkFont(size=13),
            text_color="#3a86ff",
            anchor="w"
        )
        self.video_channel_label.pack(fill="x", pady=2)

        self.video_duration_label = ctk.CTkLabel(
            self.meta_frame,
            text="Длительность: —",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w"
        )
        self.video_duration_label.pack(fill="x", pady=2)

        # 4. Секция параметров загрузки
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(fill="x", padx=20, pady=10)

        # Переключатель: Видео / Аудио
        self.mode_var = ctk.StringVar(value="video")
        self.mode_segmented = ctk.CTkSegmentedButton(
            options_frame,
            values=["Видео со звуком", "Только звук (MP3 320k)"],
            command=self._on_mode_change
        )
        self.mode_segmented.set("Видео со звуком")
        self.mode_segmented.pack(side="left", padx=15, pady=12)

        # Выпадающий список качества
        self.res_label = ctk.CTkLabel(options_frame, text="Качество:")
        self.res_label.pack(side="left", padx=(15, 5))

        self.res_option_menu = ctk.CTkOptionMenu(
            options_frame,
            values=["1080p Full HD", "720p HD", "480p", "360p", "🌟 Лучшее доступное"],
            width=170
        )
        self.res_option_menu.set("1080p Full HD")
        self.res_option_menu.pack(side="left", padx=5)

        # 5. Папка сохранения
        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", padx=20, pady=5)

        self.folder_label = ctk.CTkLabel(
            folder_frame,
            text=f"Папка: {config.download_path}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.folder_label.pack(side="left", fill="x", expand=True)

        change_folder_btn = ctk.CTkButton(
            folder_frame,
            text="Выбрать папку...",
            width=120,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._on_change_folder
        )
        change_folder_btn.pack(side="right")

        # 6. Секция прогресса и действий
        action_frame = ctk.CTkFrame(self)
        action_frame.pack(fill="x", padx=20, pady=(5, 15))

        self.progress_bar = ctk.CTkProgressBar(action_frame)
        self.progress_bar.pack(fill="x", padx=15, pady=(12, 6))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="Готов к работе",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.status_label.pack(side="left", padx=15, pady=(0, 10))

        self.finder_btn = ctk.CTkButton(
            action_frame,
            text="📂 В Finder",
            width=110,
            height=34,
            state="disabled",
            fg_color="#333333",
            command=self._on_finder_click
        )
        self.finder_btn.pack(side="right", padx=(0, 15), pady=(0, 10))

        self.download_btn = ctk.CTkButton(
            action_frame,
            text="⬇️ СКАЧАТЬ",
            width=140,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#2eb85c",
            hover_color="#248f47",
            command=self._start_download
        )
        self.download_btn.pack(side="right", padx=(0, 10), pady=(0, 10))

    def _on_paste_click(self) -> None:
        """Вставляет URL из буфера обмена."""
        text = get_clipboard_text()
        if text:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, text)
            if is_youtube_url(text):
                self._start_fetch_info()

    def _on_change_folder(self) -> None:
        """Открывает диалог выбора папки."""
        new_dir = ctk.filedialog.askdirectory(initialdir=str(config.download_path))
        if new_dir:
            config.set("download_dir", new_dir)
            self.folder_label.configure(text=f"Папка: {config.download_path}")

    def _on_mode_change(self, value: str) -> None:
        """Переключает видимость выбора разрешения при смене режима видео/аудио."""
        if "аудио" in value.lower() or "звук" in value.lower():
            self.res_option_menu.configure(state="disabled")
        else:
            self.res_option_menu.configure(state="normal")

    def _start_fetch_info(self) -> None:
        """Запускает получение метаданных в фоновом потоке."""
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Введите ссылку на видео.")
            return

        self.search_btn.configure(state="disabled")
        self.status_label.configure(text="Получение информации о видео...")

        threading.Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str) -> None:
        """Рабочий поток анализа ссылки."""
        try:
            info = extract_video_info(url)
            self.current_video_info = info

            # Загрузка обложки в память
            thumbnail_image = None
            if info.thumbnail:
                try:
                    req = Request(info.thumbnail, headers={"User-Agent": "Mozilla/5.0"})
                    with urlopen(req, timeout=5) as response:
                        img_data = response.read()
                        pil_img = Image.open(io.BytesIO(img_data))
                        thumbnail_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(240, 135))
                except Exception:
                    pass

            self.after(0, self._on_info_fetched_success, info, thumbnail_image)
        except Exception as e:
            self.after(0, self._on_info_fetched_error, str(e))

    def _on_info_fetched_success(self, info: VideoInfo, thumb_image: Optional[ctk.CTkImage]) -> None:
        """Обновление интерфейса после успешного получения метаданных."""
        self.search_btn.configure(state="normal")
        self.video_title_label.configure(text=info.title)
        self.video_channel_label.configure(text=f"Канал: {info.channel}")
        self.video_duration_label.configure(text=f"Длительность: {info.formatted_duration}")

        if thumb_image:
            self.thumb_label.configure(image=thumb_image, text="")

        # Заполняем варианты доступных качеств
        res_list = info.get_available_resolutions()
        choices = []
        if res_list:
            for r in res_list:
                label = f"{r}p"
                if r == 1080:
                    label += " (Full HD)"
                elif r >= 2160:
                    label += " (4K)"
                choices.append(label)
            choices.append("🌟 Лучшее доступное")
            self.res_option_menu.configure(values=choices)
            # Выбираем 1080p по умолчанию, если доступно
            default_choice = "1080p (Full HD)" if 1080 in res_list else choices[0]
            self.res_option_menu.set(default_choice)

        self.status_label.configure(text="Информация получена. Нажмите «СКАЧАТЬ».")
        self.download_btn.configure(state="normal")

    def _on_info_fetched_error(self, err_msg: str) -> None:
        """Отображение ошибки при неудачном анализе ссылки."""
        self.search_btn.configure(state="normal")
        self.status_label.configure(text=f"Ошибка: {err_msg[:60]}...")
        self.video_title_label.configure(text="Не удалось получить информацию о видео.")

    def _update_vpn_badge(self) -> None:
        """Регулярно обновляет статус подключения VPN в шапке окна."""
        vpn_active, vpn_name = is_vpn_active()
        if vpn_active:
            self.vpn_badge.configure(
                text=f"⚠️ VPN включен ({vpn_name})",
                text_color="#ff4757"
            )
        else:
            self.vpn_badge.configure(
                text="🟢 VPN отключен",
                text_color="#2ed573"
            )
        # Повторяем проверку каждые 4 секунды
        self.after(4000, self._update_vpn_badge)

    def _show_vpn_warning_dialog(self, vpn_name: str, on_proceed: Callable[[], None]) -> None:
        """Показывает предупреждающее модальное окно, если включен VPN."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Предупреждение: VPN активен")
        dialog.geometry("450x240")
        dialog.resizable(False, False)
        dialog.grab_set()

        msg = (
            f"⚠️ Внимание! На вашем Mac включен VPN:\n"
            f"«{vpn_name}»\n\n"
            f"Вы указали, что не хотите скачивать через VPN.\n"
            f"Пожалуйста, отключите VPN в строке меню macOS\n"
            f"для максимальной скорости и экономии трафика."
        )
        label = ctk.CTkLabel(dialog, text=msg, font=ctk.CTkFont(size=13), justify="center")
        label.pack(padx=20, pady=(25, 20))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        def cancel():
            dialog.destroy()

        def proceed():
            dialog.destroy()
            on_proceed()

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Ок, я отключу VPN",
            fg_color="#1f538d",
            command=cancel
        )
        cancel_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ignore_btn = ctk.CTkButton(
            btn_frame,
            text="Всё равно скачать",
            fg_color="#444444",
            hover_color="#555555",
            command=proceed
        )
        ignore_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _start_download(self) -> None:
        """Запускает процесс скачивания в фоновом потоке с проверкой VPN."""
        url = self.url_entry.get().strip()
        if not url:
            return

        vpn_active, vpn_name = is_vpn_active()
        if vpn_active:
            # Предупреждаем пользователя о VPN перед загрузкой
            self._show_vpn_warning_dialog(vpn_name, self._execute_download_thread)
            return

        self._execute_download_thread()

    def _execute_download_thread(self) -> None:
        """Непосредственный запуск рабочего потока скачивания."""
        url = self.url_entry.get().strip()
        if not url:
            return

        is_audio = "звук" in self.mode_segmented.get().lower()
        selected_res_raw = self.res_option_menu.get()

        # Разбор разрешения
        if "лучшее" in selected_res_raw.lower():
            resolution = "best"
        elif "1080" in selected_res_raw:
            resolution = "1080p"
        elif "720" in selected_res_raw:
            resolution = "720p"
        elif "480" in selected_res_raw:
            resolution = "480p"
        elif "360" in selected_res_raw:
            resolution = "360p"
        elif "4k" in selected_res_raw.lower() or "2160" in selected_res_raw:
            resolution = "4k"
        else:
            resolution = "1080p"

        self.download_btn.configure(state="disabled")
        self.search_btn.configure(state="disabled")
        self.finder_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(text="Подготовка к загрузке...")

        threading.Thread(
            target=self._download_worker,
            args=(url, resolution, is_audio),
            daemon=True
        ).start()


    def _download_worker(self, url: str, resolution: str, is_audio: bool) -> None:
        """Рабочий поток скачивания."""
        def on_progress(data: dict):
            status = data.get("status")
            if status == "downloading":
                percent = data.get("percent", 0.0)
                speed = data.get("speed_str", "")
                eta = data.get("eta_str", "")
                downloaded = data.get("downloaded_str", "")
                total = data.get("total_str", "")
                status_text = f"Загрузка: {percent:.1f}% ({downloaded}/{total}) • {speed} • ETA: {eta}"
                self.after(0, self._update_progress, percent / 100.0, status_text)
            elif status == "processing":
                self.after(0, self._update_progress, 1.0, "Объединение видео и аудио через FFmpeg...")
            elif status == "finished":
                self.after(0, self._update_progress, 1.0, "Завершено!")

        self.download_manager = DownloadManager(progress_callback=on_progress)

        try:
            result_path = self.download_manager.download(
                url=url,
                resolution=resolution,
                audio_only=is_audio,
                output_dir=config.download_path
            )
            self.last_downloaded_path = result_path
            self.after(0, self._on_download_success, result_path)
        except Exception as e:
            self.after(0, self._on_download_error, str(e))

    def _update_progress(self, val: float, text: str) -> None:
        """Потокобезопасное обновление прогресс-бара."""
        self.progress_bar.set(val)
        self.status_label.configure(text=text)

    def _on_download_success(self, file_path: str) -> None:
        """Действия после успешного скачивания."""
        self.download_btn.configure(state="normal")
        self.search_btn.configure(state="normal")
        self.finder_btn.configure(state="normal", fg_color="#1f538d")
        self.status_label.configure(text="✔ Видео успешно сохранено!")

        # Отправка системного уведомления macOS
        title = self.current_video_info.title if self.current_video_info else "Видео скачано"
        send_macos_notification("YouTubeDownload", "Файл успешно сохранен!", title[:40])

    def _on_download_error(self, err: str) -> None:
        """Действия при ошибке скачивания."""
        self.download_btn.configure(state="normal")
        self.search_btn.configure(state="normal")
        self.status_label.configure(text=f"Ошибка: {err[:60]}...")

    def _on_finder_click(self) -> None:
        """Открывает файл в Finder."""
        if self.last_downloaded_path:
            reveal_in_finder(self.last_downloaded_path)


def run_gui_app(initial_url: Optional[str] = None) -> None:
    """Точка запуска графического интерфейса."""
    app = YouTubeDownloadApp(initial_url=initial_url)
    app.mainloop()
