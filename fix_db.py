import psycopg2
import uuid

# Change '123456789' if your postgres password is different from the .env
DATABASE_URL = "postgresql://neondb_owner:npg_uhEk0TFQw9ni@ep-broad-term-amvjp0g2-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("Adding user_uuid column...")
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN user_uuid VARCHAR(36);")
    except psycopg2.errors.DuplicateColumn:
        print("Column already exists! Skipping addition...")
    
    print("Populating existing users with UUIDs...")
    cursor.execute("SELECT id FROM users WHERE user_uuid IS NULL;")
    rows = cursor.fetchall()
    for row in rows:
        new_uuid = str(uuid.uuid4())
        cursor.execute("UPDATE users SET user_uuid = %s WHERE id = %s", (new_uuid, row[0]))
        
    print("Adding unique constraint...")
    try:
        cursor.execute("ALTER TABLE users ADD CONSTRAINT unique_user_uuid UNIQUE (user_uuid);")
    except psycopg2.errors.DuplicateTable:
        # PostgreSQL might raise DuplicateObject or relate error if constraint exists
        pass
    except Exception as e:
        print(f"Constraint might already exist: {e}")
        
    print("Database Schema Successfully Updated! ✅")
except Exception as e:
    print(f"Failed to update database: {e}")
