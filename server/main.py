"""uvicorn entrypoint: uvicorn server.main:app --host 0.0.0.0 --port 8000"""
from server.app import create_app

app = create_app()
