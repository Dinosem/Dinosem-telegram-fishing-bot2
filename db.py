# db logic
import sqlite3
from pathlib import Path

DB_FILE = Path("data") / "game.db"
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        coins INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        rod TEXT DEFAULT 'bamboo', -- current rod id
        last_daily DATE
    );

    CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER,
        item TEXT,
        amount INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, item)
    );

    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item TEXT,
        price INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS quests (
        user_id INTEGER,
        quest_key TEXT,
        progress INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, quest_key)
    );
    """)
    conn.commit()
    conn.close()
