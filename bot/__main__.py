"""Arranque en tu PC:  python -m bot

En Render no se usa este archivo: arranca gunicorn (ver render.yaml).
"""
import os

from .app import crear_app

if __name__ == "__main__":
    app = crear_app()  # carga el .env
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
