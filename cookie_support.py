from __future__ import annotations

import base64
import os
from pathlib import Path


def _write_runtime_cookie_file(base_dir: Path, content: str) -> Path | None:
    """Write cookie content from env into a runtime file."""
    text = (content or "").strip()
    if not text:
        return None
    out_dir = base_dir / "tokens"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "cookies.runtime.txt"
    out_file.write_text(text, encoding="utf-8")
    return out_file


def _cookie_from_env(base_dir: Path) -> Path | None:
    """Materialize cookie file from env vars if present.

    Supported env vars:
    - YTDLP_COOKIES_B64: base64-encoded Netscape cookie file content.
    - YTDLP_COOKIES_TXT: plain-text Netscape cookie file content.
    """
    b64 = os.getenv("YTDLP_COOKIES_B64", "").strip()
    if b64:
        try:
            decoded = base64.b64decode(b64).decode("utf-8", errors="replace")
            return _write_runtime_cookie_file(base_dir, decoded)
        except Exception:
            return None

    raw = os.getenv("YTDLP_COOKIES_TXT", "")
    if raw.strip():
        return _write_runtime_cookie_file(base_dir, raw)
    return None


def get_cookie_candidates(base_dir: Path) -> list[Path]:
    """Return possible cookie files in priority order."""
    candidates: list[Path] = []

    env_cookie = os.getenv("YTDLP_COOKIEFILE", "").strip()
    if env_cookie:
        p = Path(env_cookie)
        if p.exists():
            candidates.append(p)

    runtime_cookie = _cookie_from_env(base_dir)
    if runtime_cookie and runtime_cookie.exists():
        candidates.append(runtime_cookie)

    for p in (base_dir / "cookies.txt", base_dir / "tokens" / "cookies.txt"):
        if p.exists():
            candidates.append(p)

    # Deduplicate while preserving order
    uniq: list[Path] = []
    seen = set()
    for p in candidates:
        k = str(p.resolve())
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq
