"""Entrypoint для запуска web API."""

import logging
import sys

import uvicorn

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

if __name__ == "__main__":
    uvicorn.run(
        "web.api:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True,
    )
