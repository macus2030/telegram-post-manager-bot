
import sqlite3
import re
from storage import DB_PATH

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# 1. Update Message Template (msg_template)
c.execute("SELECT value FROM config WHERE key = 'msg_template'")
row = c.fetchone()
if row:
    current_tmpl = row[0]
    # Remove "LN Post : {post_id}"
    new_tmpl = current_tmpl.replace("LN Post : {post_id}", "")
    # Trim leading whitespace/newlines
    new_tmpl = new_tmpl.lstrip()
    
    print(f"Updating msg_template...")
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("msg_template", new_tmpl))

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

conn.commit()
print("Database templates updated successfully.")
conn.close()
