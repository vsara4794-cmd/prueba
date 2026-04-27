"""
Añade FFmpeg al PATH del proceso si está instalado en rutas habituales
pero no expuesto globalmente (típico en Windows).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _prepend_bin(bin_dir: Path) -> None:
    d = str(bin_dir.resolve())
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if d not in parts:
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def _exe_name() -> str:
    return "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _collect_candidate_dirs() -> list[Path]:
    out: list[Path] = []
    try:
        from config import BASE_DIR

        out.append(BASE_DIR / "ffmpeg" / "bin")
    except ImportError:
        pass

    if sys.platform != "win32":
        return out

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")

    out.extend(
        [
            Path(r"C:\ffmpeg\bin"),
            Path(pf) / "ffmpeg" / "bin",
            Path(pf86) / "ffmpeg" / "bin",
            Path(r"C:\ProgramData\chocolatey\bin"),
        ]
    )

    winget_root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if winget_root.is_dir():
        try:
            # Paquetes Gyan (Essentials Build, full, etc.) — nombres varían según winget
            for pkg in winget_root.iterdir():
                if not pkg.is_dir():
                    continue
                if "Gyan" not in pkg.name or "FFmpeg" not in pkg.name:
                    continue
                for sub in pkg.iterdir():
                    if sub.is_dir() and sub.name.startswith("ffmpeg-"):
                        out.append(sub / "bin")
        except OSError:
            pass

    return out


def ensure_ffmpeg_on_path() -> bool:
    """Si ffmpeg no está en PATH, intenta localizarlo y antepone su carpeta al PATH."""
    if shutil.which("ffmpeg"):
        return True

    name = _exe_name()
    for d in _collect_candidate_dirs():
        try:
            if (d / name).is_file():
                _prepend_bin(d)
                if shutil.which("ffmpeg"):
                    return True
        except OSError:
            continue
    return False


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None
