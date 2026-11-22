"""Ścieżki cache: lokalne domyślnie, jawny katalog roboczy w chmurze."""
import os
from pathlib import Path

def cache_dir():
    return Path(os.getenv('AED_CACHE_DIR', str(Path(__file__).parent / 'data/cache')))
