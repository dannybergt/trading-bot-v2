import sqlite3
import os
from pathlib import Path

# Connect to the DB manually and run ALTER TABLE commands
DATA_DIR = Path(os.getenv("DATA_DIR", "/trading-bot/trading-bot-v2/backend/data"))
DB_PATH = DATA_DIR / "users.db"

def migrate():
    print(f"Connecting to {DB_PATH}")
    if not DB_PATH.exists():
        print("Database file doesn't exist yet, nothing to migrate.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check if columns exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]
    
    updates = []
    
    if "alpaca_api_key" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN alpaca_api_key VARCHAR")
        updates.append("alpaca_api_key")
        
    if "alpaca_secret_key" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN alpaca_secret_key VARCHAR")
        updates.append("alpaca_secret_key")
        
    if "alpaca_paper" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN alpaca_paper BOOLEAN DEFAULT 1")
        updates.append("alpaca_paper")

    if updates:
        conn.commit()
        print(f"Successfully migrated DB. Added columns: {', '.join(updates)}")
    else:
        print("Columns already exist, no migration needed.")

    conn.close()

if __name__ == "__main__":
    migrate()
