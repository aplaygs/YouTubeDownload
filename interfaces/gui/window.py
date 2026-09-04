"""
Графический интерфейс пользователя (GUI) на CustomTkinter в стиле Android 17 (Material You Expressive Dark Theme).

Особенности:
- Премиальная темная палитра Android 17: глубокий фон #121316, карточки #18191E.
- Единая математическая система скруглений (унифицированные капсулы Stadium Pill Shapes: высота 40px, радиус строго 20px).
- Фирменная типографика Apple San Francisco (.AppleSystemUIFont).
- Динамические пастельные акценты Material You: персиковый чип для видео, мятный шалфей для скачивания.
- Быстрый автоподхват ссылок из буфера обмена с информационным бейджем.
- 16:9 превью видеоролика и карточка метаданных.
- Динамический выбор качества с YouTube (включая 4K, 1440p и 60 FPS).
- Проверка и индикатор VPN в реальном времени.
- Фоновая загрузка с контролем совместимости Apple QuickTime (H.264/AAC).
"""

import io
import os
import re
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
from PIL import Image
import requests

from core.config import config
from core.downloader import DownloadManager
from core.extractor import VideoInfo, extract_video_info
from utils.clipboard import get_clipboard_text, is_youtube_url
from utils.system import open_file, reveal_in_finder, send_macos_notification
from utils.vpn import is_vpn_active

# Глобальная настройка темы
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# --- ДИЗАЙН-ТОКЕНЫ: ЦВЕТОВАЯ ПАЛИТРА ANDROID 17 MATERIAL YOU DARK ---
COLOR_BG = "#121316"              # Глубокий темный фон окна
COLOR_SURFACE = "#18191E"         # Приподнятая поверхность карточек
COLOR_SURFACE_BORDER = "#262830"  # Тонкая рамка карточек
COLOR_INPUT_BG = "#191A1F"        # Фон капсул ввода
COLOR_INPUT_BORDER = "#2B2D35"    # Рамка капсул ввода
COLOR_BTN_NEUTRAL = "#2A2C32"     # Нейтральные капсульные кнопки
COLOR_BTN_HOVER = "#363840"       # Ховер нейтральных кнопок
COLOR_ACCENT_PEACH = "#D99B90"    # Пастельный персиковый чип (активный режим видео)
COLOR_ACCENT_PEACH_HOVER = "#CE8F84"
COLOR_ACCENT_MINT = "#8EBF9B"     # Пастельный мятно-шалфейный (кнопка Скачать)
COLOR_ACCENT_MINT_HOVER = "#7EAE8B"
COLOR_TEXT_PRIMARY = "#F0F2F7"    # Высококонтрастный текст
COLOR_TEXT_SECONDARY = "#9B9FA9"  # Второстепенный текст
COLOR_TEXT_MUTED = "#6C707C"      # Заглушки и подсказки
COLOR_VPN_WARN = "#D98A8A"        # Предупреждение о VPN
COLOR_VPN_OK = "#8EBF9B"          # VPN отключен

# --- ДИЗАЙН-ТОКЕНЫ: ГЕОМЕТРИЯ И СКРУГЛЕНИЯ (ЕДИНЫЙ СТАНДАРТ) ---
# Все интерактивные капсулы (кнопки, поля ввода, селекторы) имеют строго высоту 40px и радиус 20px
HEIGHT_PILL = 40
RADIUS_PILL = 20
RADIUS_CARD = 22
RADIUS_THUMB = 16
RADIUS_TOAST = 12

# --- ДИЗАЙН-ТОКЕНЫ: ПРЕМИАЛЬНАЯ ТИПОГРАФИКА APPLE SAN FRANCISCO ---
FONT_FAMILY = ".AppleSystemUIFont"


class YouTubeDownloadApp(ctk.CTk):
    """Главное окно приложения YouTubeDownload в стиле Android 17 Dark."""

    def __init__(self, initial_url: Optional[str] = None):
        super().__init__()

        self.title("YouTubeDownload — Загрузчик видео")
        self.geometry("860x540")
        self.minsize(820, 510)
        self.configure(fg_color=COLOR_BG)

        # Шрифты
        self.font_title = ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold")
        self.font_meta = ctk.CTkFont(family=FONT_FAMILY, size=12, weight="normal")
        self.font_btn = ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold")
        self.font_btn_large = ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold")
        self.font_input = ctk.CTkFont(family=FONT_FAMILY, size=13, weight="normal")
        self.font_toast = ctk.CTkFont(family=FONT_FAMILY, size=11, weight="normal")
        self.font_status = ctk.CTkFont(family=FONT_FAMILY, size=12, weight="normal")

        self.current_video_info: Optional[VideoInfo] = None
        self.download_manager: Optional[DownloadManager] = None
        self.last_downloaded_path: Optional[str] = None
        self._current_thumb_image: Optional[ctk.CTkImage] = None
        self.current_mode: str = "video"  # "video" или "audio"

        self._setup_ui()

        # Вывод окна на передний план при открытии
        self.lift()
        self.attributes("-topmost", True)
        self.after_idle(lambda: self.attributes("-topmost", False))
        self.focus_force()

        # Если передана начальная ссылка, вставляем и сразу анализируем
        if initial_url:
            self.url_entry.insert(0, initial_url)
            self._start_fetch_info()
        else:
            # Проверяем буфер обмена при старте
            clip_text = get_clipboard_text()
            if is_youtube_url(clip_text):
                self.url_entry.insert(0, clip_text)
                self._show_toast("Ссылка обнаружена в буфере обмена. Нажмите «Найти».")

    def _setup_ui(self) -> None:
        """Инициализирует все элементы интерфейса с единой геометрией и типографикой."""

        # 1. Верхняя поисковая капсула + кнопки
        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=24, pady=(20, 4))

        self.url_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔗  https://youtu.be/... (вставьте ссылку на видео)",
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_INPUT_BG,
            border_color=COLOR_INPUT_BORDER,
            border_width=1,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_input
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._start_fetch_info())
        self.url_entry.bind("<<Paste>>", lambda e: self.after(100, self._check_and_auto_fetch))

        self.paste_btn = ctk.CTkButton(
            search_frame,
            text="📋 Вставить",
            width=105,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_BTN_NEUTRAL,
            hover_color=COLOR_BTN_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
            command=self._on_paste_click
        )
        self.paste_btn.pack(side="left", padx=(0, 8))

        self.search_btn = ctk.CTkButton(
            search_frame,
            text="🔍 Найти",
            width=95,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_BTN_NEUTRAL,
            hover_color=COLOR_BTN_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
            command=self._start_fetch_info
        )
        self.search_btn.pack(side="left")

        # Всплывающий информационный бейдж буфера обмена (под строкой поиска справа)
        self.toast_container = ctk.CTkFrame(self, fg_color="transparent", height=24)
        self.toast_container.pack(fill="x", padx=24, pady=(2, 8))

        self.toast_frame = ctk.CTkFrame(
            self.toast_container,
            fg_color="#1C1E24",
            border_color="#2B2D36",
            border_width=1,
            corner_radius=RADIUS_TOAST
        )
        self.toast_label = ctk.CTkLabel(
            self.toast_frame,
            text="ℹ️  Ссылка обнаружена в буфере обмена. Нажмите «Найти».",
            font=self.font_toast,
            text_color="#B2B6C2"
        )
        self.toast_label.pack(padx=10, pady=2)
        self.toast_frame.pack_forget()

        # 2. Центральная карточка видео (превью 16:9 + метаданные)
        self.card_frame = ctk.CTkFrame(
            self,
            fg_color=COLOR_SURFACE,
            border_color=COLOR_SURFACE_BORDER,
            border_width=1,
            corner_radius=RADIUS_CARD
        )
        self.card_frame.pack(fill="both", expand=True, padx=24, pady=(0, 10))

        # Контейнер для превью слева
        self.thumb_container = ctk.CTkFrame(
            self.card_frame,
            fg_color="#121316",
            corner_radius=RADIUS_THUMB,
            width=270,
            height=152
        )
        self.thumb_container.pack(side="left", padx=16, pady=16, anchor="center")
        self.thumb_container.pack_propagate(False)

        self.thumb_label = ctk.CTkLabel(
            self.thumb_container,
            text="🎬\n\n[ Ожидание ссылки на видео ]",
            font=self.font_meta,
            text_color=COLOR_TEXT_MUTED
        )
        self.thumb_label.pack(fill="both", expand=True)

        # Контейнер для метаданных справа
        self.meta_frame = ctk.CTkFrame(self.card_frame, fg_color="transparent")
        self.meta_frame.pack(side="left", fill="both", expand=True, padx=(10, 16), pady=16)

        self.video_title_label = ctk.CTkLabel(
            self.meta_frame,
            text="Вставьте ссылку и нажмите «Найти» для анализа видео",
            font=self.font_title,
            text_color=COLOR_TEXT_PRIMARY,
            anchor="w",
            wraplength=480,
            justify="left"
        )
        self.video_title_label.pack(fill="x", pady=(8, 10))

        self.video_channel_label = ctk.CTkLabel(
            self.meta_frame,
            text="👤  Канал: —",
            font=self.font_meta,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w"
        )
        self.video_channel_label.pack(fill="x", pady=3)

        self.video_duration_label = ctk.CTkLabel(
            self.meta_frame,
            text="⏱  Длительность: —",
            font=self.font_meta,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w"
        )
        self.video_duration_label.pack(fill="x", pady=3)

        # 3. Строка настроек: Режим (Видео/Аудио) + Качество + Индикатор VPN
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=24, pady=(2, 10))

        # Переключатель режимов: капсульные чипы единой высоты 40px и радиуса 20px
        self.mode_video_btn = ctk.CTkButton(
            controls_frame,
            text="▶  Видео со звуком",
            width=150,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_ACCENT_PEACH,
            hover_color=COLOR_ACCENT_PEACH_HOVER,
            text_color="#231210",
            font=self.font_btn,
            command=lambda: self._set_mode("video")
        )
        self.mode_video_btn.pack(side="left", padx=(0, 8))

        self.mode_audio_btn = ctk.CTkButton(
            controls_frame,
            text="🎵  Только звук (MP3 320k)",
            width=185,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color="#202126",
            hover_color="#2A2C33",
            text_color=COLOR_TEXT_SECONDARY,
            font=self.font_btn,
            command=lambda: self._set_mode("audio")
        )
        self.mode_audio_btn.pack(side="left", padx=(0, 16))

        # Выбор качества
        self.res_label = ctk.CTkLabel(
            controls_frame,
            text="Качество:",
            font=self.font_meta,
            text_color=COLOR_TEXT_SECONDARY
        )
        self.res_label.pack(side="left", padx=(0, 8))

        self.res_option_menu = ctk.CTkOptionMenu(
            controls_frame,
            values=["Качество видео..."],
            width=210,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color="#202126",
            button_color="#202126",
            button_hover_color="#2A2C33",
            dropdown_fg_color="#1C1D22",
            dropdown_hover_color="#2D2F38",
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_meta
        )
        self.res_option_menu.set("Качество видео...")
        self.res_option_menu.pack(side="left")

        # Индикатор VPN со значком щита на правом краю
        self.vpn_badge = ctk.CTkLabel(
            controls_frame,
            text="🛡️  Проверка VPN...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY
        )
        self.vpn_badge.pack(side="right")
        self._update_vpn_badge()

        # 4. Строка пути сохранения (Капсульный бокс + Кнопка единой высоты 40px и радиуса 20px)
        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", padx=24, pady=(0, 10))

        self.folder_box = ctk.CTkFrame(
            folder_frame,
            fg_color=COLOR_SURFACE,
            border_color=COLOR_SURFACE_BORDER,
            border_width=1,
            corner_radius=RADIUS_PILL,
            height=HEIGHT_PILL
        )
        self.folder_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.folder_box.pack_propagate(False)

        self.folder_label = ctk.CTkLabel(
            self.folder_box,
            text=f"📁  {config.download_path}",
            font=self.font_meta,
            text_color=COLOR_TEXT_SECONDARY,
            anchor="w"
        )
        self.folder_label.pack(side="left", fill="x", expand=True, padx=14, pady=4)

        change_folder_btn = ctk.CTkButton(
            folder_frame,
            text="📁 Выбрать...",
            width=120,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_BTN_NEUTRAL,
            hover_color=COLOR_BTN_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
            command=self._on_change_folder
        )
        change_folder_btn.pack(side="right")

        # 5. Прогресс-бар (тонкий Material капсульный бар)
        self.progress_bar = ctk.CTkProgressBar(
            self,
            height=6,
            corner_radius=3,
            fg_color="#1C1D22",
            progress_color=COLOR_ACCENT_MINT
        )
        self.progress_bar.pack(fill="x", padx=24, pady=(6, 8))
        self.progress_bar.set(0)

        # 6. Нижняя панель действий (Статус + СКАЧАТЬ + В Finder, высота 40px, радиус 20px)
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=24, pady=(0, 18))

        self.status_label = ctk.CTkLabel(
            bottom_frame,
            text="Готов к работе",
            font=self.font_status,
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.download_btn = ctk.CTkButton(
            bottom_frame,
            text="📥  СКАЧАТЬ",
            width=140,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_ACCENT_MINT,
            hover_color=COLOR_ACCENT_MINT_HOVER,
            text_color="#122617",
            font=self.font_btn_large,
            command=self._start_download
        )
        self.download_btn.pack(side="right", padx=(8, 0))

        self.finder_btn = ctk.CTkButton(
            bottom_frame,
            text="📁  В Finder",
            width=115,
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_BTN_NEUTRAL,
            hover_color=COLOR_BTN_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
            state="disabled",
            command=self._on_finder_click
        )
        self.finder_btn.pack(side="right")

    def _show_toast(self, text: str) -> None:
        """Отображает плавающий бейдж с подсказкой."""
        self.toast_label.configure(text=f"ℹ️  {text}")
        self.toast_frame.pack(side="right")

    def _hide_toast(self) -> None:
        """Скрывает плавающий бейдж."""
        self.toast_frame.pack_forget()

    def _set_mode(self, mode: str) -> None:
        """Переключает режим Видео / Аудио с обновлением стилей чипов."""
        self.current_mode = mode
        if mode == "video":
            self.mode_video_btn.configure(
                fg_color=COLOR_ACCENT_PEACH,
                hover_color=COLOR_ACCENT_PEACH_HOVER,
                text_color="#231210"
            )
            self.mode_audio_btn.configure(
                fg_color="#202126",
                hover_color="#2A2C33",
                text_color=COLOR_TEXT_SECONDARY
            )
            self.res_option_menu.configure(state="normal")
            self.res_label.configure(text_color=COLOR_TEXT_SECONDARY)
        else:
            self.mode_video_btn.configure(
                fg_color="#202126",
                hover_color="#2A2C33",
                text_color=COLOR_TEXT_SECONDARY
            )
            self.mode_audio_btn.configure(
                fg_color=COLOR_ACCENT_PEACH,
                hover_color=COLOR_ACCENT_PEACH_HOVER,
                text_color="#231210"
            )
            self.res_option_menu.configure(state="disabled")
            self.res_label.configure(text_color=COLOR_TEXT_MUTED)

    def _check_and_auto_fetch(self) -> None:
        """Автоматический запуск анализа ссылки при вставке."""
        text = self.url_entry.get().strip()
        if is_youtube_url(text):
            self._start_fetch_info()

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
            self.folder_label.configure(text=f"📁  {config.download_path}")

    def _start_fetch_info(self) -> None:
        """Запускает получение метаданных в фоновом потоке."""
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Введите ссылку на видео.")
            return

        self._hide_toast()
        self.search_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.status_label.configure(text="Анализ видео и доступных качеств...")
        self.thumb_label.configure(image=None, text="🎬\n\n[ Загрузка превью... ]")
        self.res_option_menu.configure(values=["Загрузка качеств..."])
        self.res_option_menu.set("Загрузка качеств...")

        threading.Thread(target=self._fetch_info_worker, args=(url,), daemon=True).start()

    def _fetch_info_worker(self, url: str) -> None:
        """Рабочий поток анализа ссылки и надежной загрузки обложки."""
        try:
            info = extract_video_info(url)
            self.current_video_info = info

            # Список адресов превью для попытки загрузки (JPG/WebP всех разрешений)
            candidate_thumbnails = []
            if info.thumbnail:
                candidate_thumbnails.append(info.thumbnail)
            if info.id:
                candidate_thumbnails.append(f"https://i.ytimg.com/vi/{info.id}/maxresdefault.jpg")
                candidate_thumbnails.append(f"https://i.ytimg.com/vi_webp/{info.id}/maxresdefault.webp")
                candidate_thumbnails.append(f"https://i.ytimg.com/vi/{info.id}/hqdefault.jpg")
                candidate_thumbnails.append(f"https://i.ytimg.com/vi/{info.id}/mqdefault.jpg")

            thumbnail_image = None
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            proxies = {"http": config.proxy_url, "https": config.proxy_url} if config.proxy_url else None

            for thumb_url in candidate_thumbnails:
                try:
                    try:
                        resp = requests.get(thumb_url, headers=headers, proxies=proxies, timeout=7)
                    except requests.exceptions.SSLError:
                        resp = requests.get(thumb_url, headers=headers, proxies=proxies, timeout=7, verify=False)

                    if resp.status_code == 200 and len(resp.content) > 500:
                        pil_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                        # Масштабируем до 270x152 (16:9) с сохранением четкости
                        pil_img = pil_img.resize((270, 152), Image.Resampling.LANCZOS)
                        thumbnail_image = ctk.CTkImage(
                            light_image=pil_img,
                            dark_image=pil_img,
                            size=(270, 152)
                        )
                        break
                except Exception:
                    continue

            self.after(0, self._on_info_fetched_success, info, thumbnail_image)
        except Exception as e:
            self.after(0, self._on_info_fetched_error, str(e))

    def _on_info_fetched_success(self, info: VideoInfo, thumb_image: Optional[ctk.CTkImage]) -> None:
        """Обновление интерфейса после успешного получения метаданных."""
        self.search_btn.configure(state="normal")
        self.video_title_label.configure(text=info.title)
        self.video_channel_label.configure(text=f"👤  Канал: {info.channel}")
        self.video_duration_label.configure(text=f"⏱  Длительность: {info.formatted_duration}")

        # Сохраняем ссылку на изображение для сборщика мусора
        self._current_thumb_image = thumb_image
        if thumb_image:
            self.thumb_label.configure(image=thumb_image, text="")
        else:
            self.thumb_label.configure(image=None, text="🎬\n\n[ Нет превью ]")

        # Заполняем варианты качеств strictly с YouTube для данного ролика
        quality_opts = info.get_quality_options()
        choices = []
        if quality_opts:
            for opt in quality_opts:
                choices.append(f"⚙️  {opt['label']}")
            choices.append("🌟  Максимальное качество")
            self.res_option_menu.configure(values=choices)

            # Выбираем по умолчанию 1080p, если есть, иначе первое доступное
            default_choice = choices[0]
            for c in choices:
                if "1080p" in c:
                    default_choice = c
                    break
            self.res_option_menu.set(default_choice)
        else:
            self.res_option_menu.configure(values=["🌟  Максимальное качество", "⚙️  1080p Full HD", "⚙️  720p HD"])
            self.res_option_menu.set("🌟  Максимальное качество")

        self.status_label.configure(text="Информация получена. Выберите качество и нажмите «СКАЧАТЬ».")
        self.download_btn.configure(state="normal")

    def _on_info_fetched_error(self, err_msg: str) -> None:
        """Отображение ошибки при неудачном анализе ссылки."""
        self.search_btn.configure(state="normal")
        self.status_label.configure(text=f"Ошибка: {err_msg[:60]}...")
        self.video_title_label.configure(text="Не удалось получить информацию о видео.")
        self.thumb_label.configure(image=None, text="🎬\n\n[ Ошибка загрузки ]")

    def _update_vpn_badge(self) -> None:
        """Регулярно обновляет статус подключения VPN в стиле Android 17."""
        vpn_active, vpn_name = is_vpn_active()
        if vpn_active:
            self.vpn_badge.configure(
                text=f"🛡️  VPN ON ({vpn_name})",
                text_color=COLOR_VPN_WARN
            )
        else:
            self.vpn_badge.configure(
                text="🛡️  VPN OFF",
                text_color=COLOR_VPN_OK
            )
        # Повторяем проверку каждые 4 секунды
        self.after(4000, self._update_vpn_badge)

    def _show_vpn_warning_dialog(self, vpn_name: str, on_proceed: Callable[[], None]) -> None:
        """Показывает предупреждающее модальное окно, если включен VPN."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Предупреждение: VPN активен")
        dialog.geometry("450x240")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR_SURFACE)
        dialog.grab_set()

        msg = (
            f"⚠️  Внимание! На вашем Mac включен VPN:\n"
            f"«{vpn_name}»\n\n"
            f"Вы указали, что не хотите скачивать через VPN.\n"
            f"Пожалуйста, отключите VPN в строке меню macOS\n"
            f"для максимальной скорости и экономии трафика."
        )
        label = ctk.CTkLabel(dialog, text=msg, font=self.font_meta, text_color=COLOR_TEXT_PRIMARY, justify="center")
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
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color=COLOR_BTN_NEUTRAL,
            hover_color=COLOR_BTN_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
            command=cancel
        )
        cancel_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ignore_btn = ctk.CTkButton(
            btn_frame,
            text="Всё равно скачать",
            height=HEIGHT_PILL,
            corner_radius=RADIUS_PILL,
            fg_color="#3A3C44",
            hover_color="#484B55",
            text_color=COLOR_TEXT_PRIMARY,
            font=self.font_btn,
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
            self._show_vpn_warning_dialog(vpn_name, self._execute_download_thread)
            return

        self._execute_download_thread()

    def _execute_download_thread(self) -> None:
        """Непосредственный запуск рабочего потока скачивания."""
        url = self.url_entry.get().strip()
        if not url:
            return

        is_audio = self.current_mode == "audio"
        selected_res_raw = self.res_option_menu.get()

        # Разбор разрешения и точной высоты кадра
        target_height = None
        if any(k in selected_res_raw.lower() for k in ("максимальн", "лучш")):
            resolution_str = "best"
            target_height = None
        else:
            m = re.search(r"(\d{3,4})p?", selected_res_raw)
            if m:
                target_height = int(m.group(1))
                resolution_str = f"{target_height}p"
            else:
                target_height = 1080
                resolution_str = "1080p"

        self.download_btn.configure(state="disabled")
        self.search_btn.configure(state="disabled")
        self.finder_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_label.configure(text="Подготовка к загрузке...")

        threading.Thread(
            target=self._download_worker,
            args=(url, resolution_str, target_height, is_audio),
            daemon=True
        ).start()

    def _download_worker(self, url: str, resolution: str, target_height: Optional[int], is_audio: bool) -> None:
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
                msg = data.get("message", "Обработка через FFmpeg...")
                self.after(0, self._update_progress, 1.0, msg)
            elif status == "finished":
                self.after(0, self._update_progress, 1.0, "Завершено!")

        self.download_manager = DownloadManager(progress_callback=on_progress)

        try:
            result_path = self.download_manager.download(
                url=url,
                resolution=resolution,
                target_height=target_height,
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
        self.finder_btn.configure(state="normal", fg_color=COLOR_BTN_NEUTRAL)
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
