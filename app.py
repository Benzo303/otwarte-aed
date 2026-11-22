"""Jedna aplikacja FastAPI: tryb lokalny lub uruchomienie Vercel."""
import os
if os.getenv('VERCEL')=='1' or os.getenv('AED_RUNTIME')=='vercel':
    from backend.cloud_runtime import create_cloud_app
    app=create_cloud_app()
else:
    from backend.main import app
