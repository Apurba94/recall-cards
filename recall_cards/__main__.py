"""Start the app: python -m recall_cards [data.db] [--port 8025]"""
import sys

from .fieldkit import main_cli
from .web import create_app

sys.exit(main_cli(create_app, "recall.db", 8025, sys.argv))
