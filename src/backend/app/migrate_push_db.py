import sqlite3
import os
from pathlib import Path

# Connect to the DB manually and run CREATE TABLE commands
DATA_DIR = Path(os.getenv("DATA_DIR", "/trading-bot/trading-bot-v2/backend/data"))
DB_PATH = DATA_DIR / "users.db"

def migrate():
    print(f"Connecting to {DB_PATH}")
    if not DB_PATH.exists():
        print("Database file doesn't exist yet, nothing to migrate.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Create push_subscriptions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        endpoint VARCHAR NOT NULL UNIQUE,
        p256dh VARCHAR NOT NULL,
        auth VARCHAR NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_push_subscriptions_id ON push_subscriptions (id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id ON push_subscriptions (user_id);")

    conn.commit()
    print("Successfully created push_subscriptions table.")

    conn.close()

if __name__ == "__main__":
    migrate()
