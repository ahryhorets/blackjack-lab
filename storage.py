"""
storage.py - saving games, session history, and the hand log.

STUDY NOTES
- JSON turns Python dicts/lists into text and back. json.dump writes,
  json.load reads.
- Writing safely: write to a temporary file first, then os.replace() it over
  the real one. If the program crashes half-way, the old file is still whole.
- hands.jsonl = "JSON lines": one JSON object per line. Appending one line
  per hand is cheap and a broken last line can't damage the earlier ones.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SAVE_FILE = os.path.join(DATA_DIR, "save.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HANDS_FILE = os.path.join(DATA_DIR, "hands.jsonl")


def _ensure_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _write_json(path: str, obj) -> None:
    _ensure_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# ---- game in progress ------------------------------------------------
def save_game(state: dict) -> None:
    _write_json(SAVE_FILE, state)


def load_game() -> dict | None:
    return _read_json(SAVE_FILE, None)


def clear_game() -> None:
    if os.path.exists(SAVE_FILE):
        os.remove(SAVE_FILE)


# ---- finished sessions ----------------------------------------------
def load_history() -> list[dict]:
    return _read_json(HISTORY_FILE, [])


def append_history(summary: dict) -> None:
    hist = load_history()
    hist.append(summary)
    _write_json(HISTORY_FILE, hist)


# ---- every hand -----------------------------------------------------
def log_hand(record: dict) -> None:
    _ensure_dir()
    record = dict(record, time=datetime.now().isoformat(timespec="seconds"))
    with open(HANDS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_hands(player: str | None = None) -> list[dict]:
    out = []
    try:
        with open(HANDS_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if player is None or rec.get("player") == player:
                    out.append(rec)
    except FileNotFoundError:
        pass
    return out
