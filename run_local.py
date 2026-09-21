"""Local scheduled entry point. Private settings stay in data/local-config.json."""
import json
import os
from pathlib import Path
import subprocess
import sys
import socket

root = Path(__file__).resolve().parent
settings = json.loads((root/'data/local-config.json').read_text('utf-8'))
for key, value in settings['loader_env'].items():
    os.environ[key] = str(value)
if settings.get('pg_ctl'):
    command = [settings['pg_ctl'], '-D', settings['pg_data']]
    try:
        with socket.create_connection((os.environ['PGHOST'],int(os.environ['PGPORT'])),timeout=3):
            running=True
    except OSError:
        running=False
    if not running:
        subprocess.run(command+['-l', str(root/'logs/postgres.log'),
            '-o', '-h 127.0.0.1 -p 55440', '-w', 'start'], check=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
from etl import main
raise SystemExit(main())
