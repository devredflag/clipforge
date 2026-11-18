"""`python -m app` — inicia o servidor local (somente neste computador, por padrão)."""
import logging
import os

import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("CLIPFORGE_HOST", "127.0.0.1"),
        port=int(os.environ.get("CLIPFORGE_PORT", "8765")),
        log_level="info",
    )
