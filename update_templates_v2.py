
import sqlite3
import os

# Try common paths
db_path = "bot.db"
if not os.path.exists(db_path):
    # Try looking in typical Render/persistence paths if needed, 
    # but for local dev (User's machine), it's usually at root.
    pass

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Update Message Template (msg_template)
    c.execute("SELECT value FROM config WHERE key = 'msg_template'")
    row = c.fetchone()
    if row:
        current_tmpl = row[0]
        if "LN Post : {post_id}" in current_tmpl:
            # Remove "LN Post : {post_id}"
            new_tmpl = current_tmpl.replace("LN Post : {post_id}", "")
            # Trim leading whitespace/newlines
            new_tmpl = new_tmpl.lstrip()
            
            print(f"Updating msg_template...")
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("msg_template", new_tmpl))
        else:
             print("msg_template already clean.")

    # 2. Update Main Channel Template (main_template)
    c.execute("SELECT value FROM config WHERE key = 'main_template'")
    row = c.fetchone()
    if row:
        current_tmpl = row[0]
        # Replace "Post :- LN{post_id}" with "Post :- {post_id}"
        if "Post :- LN{post_id}" in current_tmpl:
            new_tmpl = current_tmpl.replace("Post :- LN{post_id}", "Post :- {post_id}")
            print(f"Updating main_template...")
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("main_template", new_tmpl))
        else:
            print("main_template already clean.")

    conn.commit()
    print("Database check/update completed.")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
