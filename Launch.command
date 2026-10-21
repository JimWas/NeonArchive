#!/bin/zsh
cd "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  echo 'First-time setup: creating the Python environment…'
  python3 -m venv .venv || exit 1
fi
.venv/bin/python -c 'import PySide6, requests, bs4' 2>/dev/null || .venv/bin/python -m pip install -r requirements.txt || exit 1
exec .venv/bin/python app.py
