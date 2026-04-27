import re
import uuid
import os

import yt_dlp
from pathlib import Path

from config import BASE_DIR, DOWNLOADS_DIR
from subprocess_utils import run as _run

# Prefer H.264 (avc1) which every ffmpeg supports.
# Fallback chain avoids AV1/VP9 codec issues on Windows.
_FORMAT = (
    "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[acodec^=mp4a]/"
    "bestvideo[vcodec^=avc1][height<=1080]+bestaudio/"
    "bestvideo[height<=1080]+bestaudio/"
    "best"
)

_YT_BOT_HINTS = (
    "sign in to confirm you're not a bot",
    "use --cookies-from-browser",
    "please sign in",
    "http error 403",
    "this video is unavailable",
)
_COOKIE_BROWSERS = ("edge", "chrome", "firefox")


def _is_bot_block_error(err: Exception) -> bool:
    msg = str(err).lower()
    return any(h in msg for h in _YT_BOT_HINTS)


def _cookie_candidates() -> list[Path]:
    """Possible cookie files in priority order."""
    env_cookie = os.getenv("YTDLP_COOKIEFILE")
    candidates: list[Path] = []
    if env_cookie:
        candidates.append(Path(env_cookie))
    candidates.append(BASE_DIR / "cookies.txt")
    candidates.append(BASE_DIR / "tokens" / "cookies.txt")
    return [p for p in candidates if p.exists()]


def download_video(url: str, output_dir: Path = DOWNLOADS_DIR) -> Path:
    """Download a YouTube video and return the file path."""
    output_dir.mkdir(exist_ok=True)

    base_opts = {
        "format": _FORMAT,
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "restrictfilenames": True,   # ASCII-safe names (no unicode quotes etc.)
        "quiet": False,
        "no_warnings": True,
        # Helps with some YouTube anti-bot checks.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "retries": 3,
        "fragment_retries": 3,
        "noplaylist": True,
    }

    def _run(extra_opts: dict | None = None) -> Path:
        opts = dict(base_opts)
        if extra_opts:
            opts.update(extra_opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return Path(filename)

    try:
        return _run()
    except Exception as e:
        if not _is_bot_block_error(e):
            raise
        # 1) Try explicit cookie files (works in cloud/local).
        for cookies_path in _cookie_candidates():
            try:
                print(f"[i] Intentando con cookies.txt: {cookies_path}")
                return _run({"cookiefile": str(cookies_path)})
            except Exception as ce:
                print(f"[i] Falló cookies.txt: {ce}")

        # 2) Try browser cookies (local desktop only).
        print("[i] YouTube pidió verificación anti-bot; probando cookies del navegador…")
        for browser in _COOKIE_BROWSERS:
            try:
                print(f"[i] Intentando con cookies de {browser}…")
                return _run({"cookiesfrombrowser": (browser,)})
            except Exception as be:
                print(f"[i] Falló {browser}: {be}")
        raise RuntimeError(
            "YouTube bloqueó la descarga. Inicia sesión en YouTube en Edge o Chrome "
            "y vuelve a intentar, o coloca un cookies.txt válido en la carpeta del proyecto."
        ) from e


def _ffprobe_duration(path: Path) -> float:
    r = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr or "ffprobe falló")
    return float(r.stdout.strip())


def trim_video_to_segment(
    video_path: Path,
    start_sec: float,
    end_sec: float | None,
    output_dir: Path = DOWNLOADS_DIR,
) -> Path:
    """Recorta un vídeo a [start_sec, end_sec). Si end_sec es None, hasta el final.

    El archivo de salida va a output_dir. No borra el original (lo hace el llamador si aplica).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if start_sec < 0:
        start_sec = 0.0

    duration_total = _ffprobe_duration(video_path)
    if start_sec >= duration_total:
        raise ValueError(
            f"El inicio del tramo ({start_sec:.1f}s) es mayor o igual que la duración del vídeo ({duration_total:.1f}s)."
        )

    end = float(end_sec) if end_sec is not None else duration_total
    if end > duration_total:
        end = duration_total
    if end <= start_sec:
        raise ValueError("El fin del tramo debe ser mayor que el inicio.")

    length = end - start_sec
    safe_stem = re.sub(r"[^\w\-]+", "_", video_path.stem)[:36]
    out = output_dir / f"{safe_stem}_tramo_{int(start_sec)}_{int(end)}_{uuid.uuid4().hex[:6]}.mp4"

    # Intento rápido con copia de flujo; si falla, re-codifica (más compatible).
    cmd_copy = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(video_path),
        "-t",
        str(length),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out),
    ]
    r = _run(cmd_copy, capture_output=True, text=True, timeout=None)
    if r.returncode == 0 and out.exists() and out.stat().st_size > 1000:
        return out

    if out.exists():
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass

    cmd_enc = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(video_path),
        "-t",
        str(length),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(out),
    ]
    r2 = _run(cmd_enc, capture_output=True, text=True, timeout=None)
    if r2.returncode != 0 or not out.exists():
        err = (r2.stderr or r2.stdout or r.stderr or "")[-2000:]
        raise RuntimeError(f"No se pudo recortar el vídeo: {err}")
    return out
