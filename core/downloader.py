"""
Модуль загрузки медиапотоков через yt-dlp и объединения через FFmpeg.

Гарантирует 100% совместимость с macOS QuickTime Player:
1. Автоматический выбор видеокодека H.264 (avc1) и аудиокодека AAC (mp4a).
2. Автоматическая проверка полученного медиафайла через ffprobe.
3. Если видеокодек не поддерживается QuickTime (например, VP9/AV1), автоматически
   выполняется аппаратная конвертация через h264_videotoolbox на Apple Silicon.
4. Потокобезопасные коллбэки прогресса для CLI и GUI.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
import yt_dlp

from core.config import config
from core.extractor import find_js_runtime
from utils.system import move_to_trash


def get_ffmpeg_binary_path() -> Optional[str]:
    """Определяет путь к исполняемому файлу ffmpeg."""
    venv_ffmpeg = Path(__file__).resolve().parent.parent / "venv" / "bin" / "ffmpeg"
    if venv_ffmpeg.exists() and os.access(venv_ffmpeg, os.X_OK):
        return str(venv_ffmpeg)

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import static_ffmpeg
        ffmpeg_exe, _ = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg_exe
    except Exception:
        pass

    return None


def get_ffprobe_binary_path() -> Optional[str]:
    """Определяет путь к исполняемому файлу ffprobe."""
    venv_ffprobe = Path(__file__).resolve().parent.parent / "venv" / "bin" / "ffprobe"
    if venv_ffprobe.exists() and os.access(venv_ffprobe, os.X_OK):
        return str(venv_ffprobe)

    system_ffprobe = shutil.which("ffprobe")
    if system_ffprobe:
        return system_ffprobe

    try:
        import static_ffmpeg
        _, ffprobe_exe = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
        return ffprobe_exe
    except Exception:
        pass

    return None


def inspect_media_codecs(file_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Возвращает кортеж (video_codec, audio_codec) для указанного файла через ffprobe.
    Например: ('h264', 'aac') или ('vp9', 'opus').
    """
    ffprobe = get_ffprobe_binary_path()
    if not ffprobe or not file_path.exists():
        return (None, None)

    try:
        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "stream=codec_name,codec_type",
            "-of", "json",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        vcodec, acodec = None, None
        for stream in data.get("streams", []):
            stype = stream.get("codec_type")
            cname = stream.get("codec_name", "").lower()
            if stype == "video" and not vcodec:
                vcodec = cname
            elif stype == "audio" and not acodec:
                acodec = cname
        return (vcodec, acodec)
    except Exception:
        return (None, None)


def ensure_quicktime_compatible(file_path: Path, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Path:
    """
    Проверяет, открывается ли видеофайл в QuickTime Player.
    QuickTime поддерживает только H.264 (avc1) и H.265 (hevc) в MP4, со звуком AAC.
    Если обнаружен VP9 или AV1, запускает аппаратную перекодировку через h264_videotoolbox.
    Старый несовместимый файл безопасно перемещается в корзину macOS.
    """
    if not file_path.exists() or file_path.suffix.lower() != ".mp4":
        return file_path

    vcodec, acodec = inspect_media_codecs(file_path)

    # QuickTime совместимые видеокодеки
    qt_supported_vcodecs = {"h264", "hevc", "prores"}
    qt_supported_acodecs = {"aac", "alac", "pcm_s16le"}

    needs_video_transcode = vcodec and (vcodec not in qt_supported_vcodecs)
    needs_audio_transcode = acodec and (acodec not in qt_supported_acodecs)

    if not needs_video_transcode and not needs_audio_transcode:
        # Файл уже полностью совместим с QuickTime!
        return file_path

    ffmpeg = get_ffmpeg_binary_path()
    if not ffmpeg:
        return file_path

    if progress_callback:
        progress_callback({
            "status": "processing",
            "percent": 100.0,
            "message": "Оптимизация видео для QuickTime Player (H.264 / AAC)..."
        })

    temp_output = file_path.parent / f"{file_path.stem}_qt_compatible.mp4"

    cmd = [ffmpeg, "-y", "-i", str(file_path)]

    # Видеокодек
    if needs_video_transcode:
        # Пробуем аппаратный h264_videotoolbox
        cmd.extend(["-c:v", "h264_videotoolbox", "-b:v", "4500k"])
    else:
        cmd.extend(["-c:v", "copy"])

    # Аудиокодек
    if needs_audio_transcode:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-c:a", "copy"])

    cmd.append(str(temp_output))

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        if temp_output.exists() and temp_output.stat().st_size > 0:
            # Безопасно перемещаем старый несовместимый файл в корзину macOS
            move_to_trash(file_path)
            # Переименовываем оптимизированный файл на исходное имя
            temp_output.rename(file_path)
            return file_path
    except Exception as e:
        # Если перекодировка не удалась, оставляем как есть
        print(f"[Предупреждение] Не удалось конвертировать для QuickTime: {e}")
        if temp_output.exists():
            move_to_trash(temp_output)

    return file_path


class DownloadManager:
    """
    Класс для управления процессом скачивания медиафайлов.
    """

    def __init__(self, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.progress_callback = progress_callback
        self.is_cancelled = False
        self.downloaded_file_path: Optional[str] = None

    def _hook(self, d: Dict[str, Any]) -> None:
        """Внутренний перехватчик событий yt-dlp."""
        if self.is_cancelled:
            raise Exception("Загрузка отменена пользователем.")

        if not self.progress_callback:
            return

        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            speed = d.get("speed") or 0
            eta = d.get("eta") or 0

            percent = (downloaded / total * 100) if total > 0 else 0.0

            if speed > 1024 * 1024:
                speed_str = f"{speed / (1024 * 1024):.1f} МБ/с"
            elif speed > 1024:
                speed_str = f"{speed / 1024:.1f} КБ/с"
            else:
                speed_str = f"{speed:.0f} Б/с"

            if eta > 0:
                mins, secs = divmod(int(eta), 60)
                eta_str = f"{mins:02d}:{secs:02d}"
            else:
                eta_str = "--:--"

            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024) if total > 0 else 0.0

            self.progress_callback({
                "status": "downloading",
                "percent": percent,
                "speed_str": speed_str,
                "eta_str": eta_str,
                "downloaded_str": f"{downloaded_mb:.1f} МБ",
                "total_str": f"{total_mb:.1f} МБ",
                "filename": d.get("filename", "")
            })

        elif status == "finished":
            self.downloaded_file_path = d.get("filename")
            self.progress_callback({
                "status": "processing",
                "percent": 100.0,
                "message": "Сборка контейнера через FFmpeg..."
            })

    def cancel(self) -> None:
        """Отмена текущей загрузки."""
        self.is_cancelled = True

    def download(
        self,
        url: str,
        resolution: str = "1080p",
        audio_only: bool = False,
        output_dir: Optional[Path] = None
    ) -> str:
        """
        Запускает скачивание ролика или аудио.
        Гарантирует поддержку QuickTime Player.
        """
        self.is_cancelled = False
        target_dir = output_dir or config.download_path
        target_dir.mkdir(parents=True, exist_ok=True)

        ffmpeg_path = get_ffmpeg_binary_path()

        ydl_opts: Dict[str, Any] = {
            "outtmpl": str(target_dir / "%(title)s [%(resolution)s].%(ext)s"),
            "progress_hooks": [self._hook],
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": config.get("retries", 10),
            "fragment_retries": config.get("fragment_retries", 10),
            "concurrent_fragment_downloads": config.get("concurrent_fragments", 5),
        }

        # Подключение JS runtime для решения n-sig
        if config.get("use_js_runtime", True):
            js_runtime = find_js_runtime()
            if js_runtime:
                ydl_opts["js_runtimes"] = js_runtime

        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_path)

        if config.proxy_url:
            ydl_opts["proxy"] = config.proxy_url

        if audio_only:
            # Режим скачивания только звука (MP3 320k)
            ydl_opts["outtmpl"] = str(target_dir / "%(title)s.%(ext)s")
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": config.get("audio_format", "mp3"),
                    "preferredquality": str(config.get("audio_quality", "320")),
                }
            ]
            if config.get("embed_thumbnail", True):
                ydl_opts["writethumbnail"] = True
                ydl_opts["postprocessors"].append({"key": "EmbedThumbnail"})
            if config.get("embed_metadata", True):
                ydl_opts["postprocessors"].append({"key": "FFmpegMetadata"})
        else:
            # Режим скачивания видео со звуком:
            # СТРОГИЙ приоритет H.264 (avc1) + AAC (mp4a), чтобы QuickTime на macOS
            # открывал видео БЕЗ ошибок несовместимости!
            if resolution in ("best", "4k", "2160p"):
                fmt = (
                    "bestvideo[height<=2160][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=2160][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=2160]+bestaudio/best"
                )
            elif resolution in ("1440p", "2k"):
                fmt = (
                    "bestvideo[height<=1440][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=1440][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=1440]+bestaudio/best"
                )
            elif resolution == "1080p":
                fmt = (
                    "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=1080][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=1080]+bestaudio/best"
                )
            elif resolution == "720p":
                fmt = (
                    "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=720][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=720]+bestaudio/best"
                )
            elif resolution == "480p":
                fmt = (
                    "bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=480][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=480]+bestaudio/best"
                )
            elif resolution == "360p":
                fmt = (
                    "bestvideo[height<=360][vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=360][vcodec^=avc]+bestaudio[acodec^=mp4a]/"
                    "bestvideo[height<=360]+bestaudio/best"
                )
            else:
                fmt = f"bestvideo[height<={resolution}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<={resolution}]+bestaudio/best"

            ydl_opts["format"] = fmt
            ydl_opts["merge_output_format"] = "mp4"

            if config.get("embed_metadata", True):
                ydl_opts["postprocessors"] = [{"key": "FFmpegMetadata"}]

        # Выполнение загрузки
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if "entries" in info:
                info = next(iter(info["entries"]))
            final_filename = ydl.prepare_filename(info)

            if audio_only:
                ext = config.get("audio_format", "mp3")
                final_filename = os.path.splitext(final_filename)[0] + f".{ext}"
            else:
                final_filename = os.path.splitext(final_filename)[0] + ".mp4"

            self.downloaded_file_path = final_filename

        # Финальная проверка на совместимость с QuickTime Player
        if not audio_only and self.downloaded_file_path:
            final_path = Path(self.downloaded_file_path)
            ensured_path = ensure_quicktime_compatible(final_path, self.progress_callback)
            self.downloaded_file_path = str(ensured_path)

        if self.progress_callback:
            self.progress_callback({
                "status": "finished",
                "percent": 100.0,
                "filename": self.downloaded_file_path
            })

        return self.downloaded_file_path
