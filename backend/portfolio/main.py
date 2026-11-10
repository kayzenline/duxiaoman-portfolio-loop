"""ASGI entrypoint: `uvicorn portfolio.main:app`. DB path from PORTFOLIO_DB (default data/portfolio.db)."""
import os
from pathlib import Path

from .api import create_app

ROOT = Path(__file__).resolve().parents[2]
app = create_app(os.environ.get('PORTFOLIO_DB', ROOT / 'data' / 'portfolio.db'))
