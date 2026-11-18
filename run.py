#!/usr/bin/env python3
"""Atalho para iniciar o ClipForge: `python run.py`.

Equivale a `cd backend && python -m app`. Inicia o servidor local (só neste computador por padrão).
"""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
sys.path.insert(0, BACKEND)

if __name__ == "__main__":
    import logging

    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("CLIPFORGE_HOST", "127.0.0.1"),
        port=int(os.environ.get("CLIPFORGE_PORT", "8765")),
        log_level="info",
    )
