#!/usr/bin/env python3
"""
ViriaRevive  –  Viral Clip Generator

  Downloads a YouTube video, finds the most engaging moments (no AI –
  pure audio-energy + scene-change analysis), adds TikTok-style
  word-by-word subtitles, and optionally schedules uploads to YouTube.

Usage:
  python main.py "https://youtube.com/watch?v=VIDEO_ID"
  python main.py "URL" --clips 3 --duration 45 --style bold
  python main.py "URL" --upload --schedule 12
"""

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from config import (
    CLIPS_DIR,
    CLIP_DURATION,
    CROP_VERTICAL,
    FFMPEG_PRESET,
    MIN_GAP,
    NUM_CLIPS,
    SUBTITLE_STYLE,
    SUBTITLES_DIR,
    VIDEO_CRF,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
)
from downloader import download_video
from detector import find_viral_moments
from transcriber import transcribe_clip
from subtitler import generate_subtitles
from clipper import extract_clip, extract_audio_clip
from cropper import get_crop_params, get_dimensions
from uploader import upload_to_youtube, build_schedule


def _check_deps():
    from ffmpeg_locate import ensure_ffmpeg_on_path

    if not ensure_ffmpeg_on_path() and not shutil.which("ffmpeg"):
        print('[!] No se encontró ffmpeg – prueba: winget install "FFmpeg (Essentials Build)" o coloca ffmpeg/bin junto a la app.')
        print("    https://www.gyan.dev/ffmpeg/builds/")
        sys.exit(1)


def process(
    url: str,
    num_clips: int = NUM_CLIPS,
    clip_duration: int = CLIP_DURATION,
    style: str = SUBTITLE_STYLE,
    model: str = WHISPER_MODEL,
    language: str = WHISPER_LANGUAGE,
    upload: bool = False,
    schedule_hours: int = 24,
    crop: bool = CROP_VERTICAL,
):
    _check_deps()

    # ── 1. Download ──────────────────────────────────────────────────────
    print("\n══ 1 · Descargando vídeo ══")
    video_path = download_video(url)
    print(f"[+] {video_path}")

    # ── 2. Detect viral moments ──────────────────────────────────────────
    print("\n══ 2 · Buscando momentos virales ══")
    moments = find_viral_moments(
        video_path, num_clips=num_clips, clip_duration=clip_duration, min_gap=MIN_GAP
    )
    if not moments:
        print("[!] No se encontró nada – prueba un vídeo más largo o reduce --clips")
        return []

    # ── 3. Clip + subtitle each moment ───────────────────────────────────
    print("\n══ 3 · Creando clips con subtítulos ══")
    stem = video_path.stem[:50]
    done: list[Path] = []

    for idx, m in enumerate(moments, 1):
        print(f"\n── Clip {idx} de {len(moments)} ──")
        start, end = m["start"], m["end"]

        # 3a. compute crop params for 9:16
        crop_params = None
        vid_w, vid_h = get_dimensions(video_path)
        if crop:
            crop_params = get_crop_params(video_path, start, end)
            if crop_params:
                vid_w, vid_h = crop_params[0], crop_params[1]

        # 3b. extract wav for whisper
        wav = SUBTITLES_DIR / f"{stem}_c{idx}.wav"
        if not extract_audio_clip(video_path, start, end, wav):
            continue

        # 3c. transcribe → word timestamps
        words = transcribe_clip(wav, model_size=model, language=language)

        # 3d. build ASS subtitles (sized for cropped resolution)
        ass = SUBTITLES_DIR / f"{stem}_c{idx}.ass"
        generate_subtitles(words, ass, video_width=vid_w, video_height=vid_h, style=style)

        # 3e. extract clip + crop + burn subs (single ffmpeg pass)
        out = CLIPS_DIR / f"{stem}_viral{idx}.mp4"
        result = extract_clip(
            video_path, start, end, out,
            subtitle_path=ass if words else None,
            crop_params=crop_params,
            preset=FFMPEG_PRESET,
            crf=VIDEO_CRF,
        )
        if result:
            done.append(result)

        # cleanup temp wav
        wav.unlink(missing_ok=True)

    print(f"\n══ ¡Listo! {len(done)} clips ══")
    for p in done:
        print(f"  → {p}")

    # ── 4. Upload / schedule ─────────────────────────────────────────────
    if upload and done:
        print("\n══ 4 · Subiendo a YouTube ══")
        sched = build_schedule(
            done,
            start_time=datetime.utcnow() + timedelta(hours=1),
            interval_hours=schedule_hours,
        )
        for item in sched:
            idx = done.index(item["path"]) + 1
            upload_to_youtube(
                item["path"],
                title=f"{stem} – Clip viral #{idx}",
                description=f"Clip viral de {stem}\n\n#shorts #viral",
                scheduled_time=item["scheduled_time"],
            )

    return done


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(
        description="ViriaRevive – generador de clips virales",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("url", help="URL del vídeo de YouTube")
    p.add_argument("-n", "--clips",    type=int, default=NUM_CLIPS,    help=f"número de clips (por defecto {NUM_CLIPS})")
    p.add_argument("-d", "--duration", type=int, default=CLIP_DURATION, help=f"duración del clip en segundos (por defecto {CLIP_DURATION})")
    p.add_argument("-s", "--style",    choices=["tiktok", "clean", "bold"], default=SUBTITLE_STYLE, help="estilo de subtítulos")
    p.add_argument("-m", "--model",    choices=["tiny", "base", "small", "medium", "large-v3"], default=WHISPER_MODEL, help="tamaño del modelo Whisper")
    p.add_argument("-l", "--language", default=WHISPER_LANGUAGE, help="forzar idioma (en, es, fr …)")
    p.add_argument("-u", "--upload",   action="store_true", help="subir clips a YouTube")
    p.add_argument("--schedule",       type=int, default=24, help="horas entre subidas programadas")
    p.add_argument("--no-crop",        action="store_true", help="desactivar recorte vertical 9:16")

    a = p.parse_args()
    process(
        url=a.url,
        num_clips=a.clips,
        clip_duration=a.duration,
        style=a.style,
        model=a.model,
        language=a.language,
        upload=a.upload,
        schedule_hours=a.schedule,
        crop=not a.no_crop,
    )


if __name__ == "__main__":
    main()
