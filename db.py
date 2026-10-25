import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "emart.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def get_connection():
    """Open a connection. Foreign keys must be switched on EVERY time in SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # lets us use row["name"]
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables from schema.sql (this wipes existing data)."""
    conn = get_connection()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()