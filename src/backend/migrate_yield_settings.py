import sqlite3
import os

DB_PATH = '/app/data/users.db'

def migrate():
    print(f"Connecting to database at {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if trade_fee_absolute column exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]

        if "trade_fee_absolute" not in columns:
            print("Adding trade_fee_absolute to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN trade_fee_absolute INTEGER DEFAULT 1")
            
        if "trade_fee_percent" not in columns:
            print("Adding trade_fee_percent to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN trade_fee_percent INTEGER DEFAULT 0")
            
        if "min_target_yield" not in columns:
            print("Adding min_target_yield to users table...")
            cursor.execute("ALTER TABLE users ADD COLUMN min_target_yield INTEGER DEFAULT 2")

        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
