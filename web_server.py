#!/usr/bin/env python3
"""
ViriaRevive — modo web (MVP local).

Sirve la carpeta gui/ y expone la misma ApiBridge vía HTTP para el navegador.
Por defecto solo escucha en 127.0.0.1 (tu máquina).

  python web_server.py
  python web_server.py --host 0.0.0.0 --port 8765

Requisitos: mismas dependencias que la app de escritorio (FFmpeg en PATH, etc.).
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from api_bridge import ApiBridge

GUI_DIR = Path(__file__).resolve().parent / "gui"

_bridge: ApiBridge | None = None

app = FastAPI(title="ViriaRevive", version="0.1-web")


class RpcBody(BaseModel):
    method: str
    args: list[Any] = Field(default_factory=list)


@app.on_event("startup")
def _startup() -> None:
    global _bridge
    _bridge = ApiBridge()
    # Sin ventana pywebview: _js encola y el navegador consume vía /api/pending-js


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "web"}


@app.get("/api/pending-js")
def pending_js() -> dict[str, list[str]]:
    if _bridge is None:
        raise HTTPException(503, "El puente API no está listo")
    return _bridge.drain_pending_js_web()


@app.post("/api/rpc")
def rpc_call(body: RpcBody) -> JSONResponse:
    if _bridge is None:
        raise HTTPException(503, "El puente API no está listo")
    name = body.method
    if not name or name.startswith("_"):
        raise HTTPException(400, "Nombre de método no válido")
    fn = getattr(_bridge, name, None)
    if fn is None or not callable(fn):
        raise HTTPException(404, f"Método desconocido: {name}")
    try:
        result = fn(*body.args)
    except TypeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        return JSONResponse(
            {"error": str(e), "traceback": traceback.format_exc()},
            status_code=500,
        )
    try:
        json.dumps(result)
    except TypeError:
        result = json.loads(json.dumps(result, default=str))
    return JSONResponse({"result": result})


app.mount(
    "/",
    StaticFiles(directory=str(GUI_DIR), html=True),
    name="gui",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor web ViriaRevive (MVP local)")
    parser.add_argument("--host", default="127.0.0.1", help="Dirección de escucha (usa 0.0.0.0 para LAN)")
    parser.add_argument("--port", type=int, default=8765, help="Puerto TCP")
    args = parser.parse_args()

    if not GUI_DIR.is_dir():
        raise SystemExit(f"No existe la carpeta GUI: {GUI_DIR}")

    uvicorn.run(
        "web_server:app",
        host=args.host,
        port=args.port,
        reload=False,
        factory=False,
    )


if __name__ == "__main__":
    main()
