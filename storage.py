import sqlite3
import json
import os
import threading
import time
from typing import Dict, Any, Optional, List, Tuple

import threading
import time
from typing import Dict, Any, Optional, List, Tuple

# Check for Render persistent disk
if os.path.exists("/data"):
    DB_FILE = "/data/bot.db"
    DATA_FILE = "/data/data.json" # For migration if needed, or ignored
else:
    DB_FILE = "bot.db"
    DATA_FILE = "data.json"

lock = threading.Lock()

# Defaults from original storage.py
INITIAL_MSG_TEMPLATE = """LN Post : {post_id}

{caption}

Download / Watch Link 👇🏻
{short_link}

How to Open
https://t.me/Hungama1/{channel_post_id}"""

INITIAL_MAIN_TEMPLATE = """📢 <b>Main Channel Post</b>

{news}

ISKO IGNORE KARO, VIDEOS KI LINK NICHE HAI..😉
.
.
.
Post :- LN{post_id}

👉 <a href="{bot_deep_link}">CLICK HERE TO OPEN POST</a>
👉 <a href="{bot_deep_link}">CLICK HERE TO OPEN POST</a>

How to Use Telegram Bot?
{how_to_open_link}"""

def get_connection():
    # check_same_thread=False allows sharing connection, but we should be careful.
    # Ideally use a new connection per thread or context.
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Posts Table
    # storing full JSON in 'data' for flexibility
    c.execute("""CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        status TEXT,
        category TEXT,
        views INTEGER DEFAULT 0,
        created_at INTEGER,
        data TEXT
    )""")
    
    # Categories Table
    c.execute("""CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )""")
    
    # Config/Templates Table
    c.execute("""CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    conn.commit()
    
    # Check if posts exist, if not, try migrate
    c.execute("SELECT count(*) FROM posts")
    count = c.fetchone()[0]
    
    # Migration Logic
    # 1. Check if DATA_FILE (persistent) exists? (Unlikely on first run)
    # 2. If not, check "data.json" in current directory (Source)
    
    source_json = DATA_FILE
    if not os.path.exists(source_json):
        # Fallback to local file in current dir (repo file)
        if os.path.exists("data.json"):
            source_json = "data.json"
    
    if count == 0 and os.path.exists(source_json):
        try:
            print(f"Migrating from {source_json}...")
            migrate_from_json(conn, source_json)
        except Exception as e:
            print(f"Migration Error: {e}")
    elif count == 0:
        # Init defaults
        defaults = ["Movies", "Series", "Other"]
        for d in defaults:
            c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (d,))
            
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ("msg_template", INITIAL_MSG_TEMPLATE))
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ("main_template", INITIAL_MAIN_TEMPLATE))
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", ("help_link", "https://t.me/example_tutorial"))
        conn.commit()

    conn.close()

def migrate_from_json(conn, file_path):
    print(f"Starting Migration from {file_path}...")
    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except:
            return # Empty or invalid

    c = conn.cursor()
    
    # Text Templates
    if "msg_template" in data:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("msg_template", data["msg_template"]))
    else:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("msg_template", INITIAL_MSG_TEMPLATE))

    if "main_template" in data:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("main_template", data["main_template"]))
    else:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("main_template", INITIAL_MAIN_TEMPLATE))
        
    if "help_link" in data:
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("help_link", data["help_link"]))
        
    # Categories
    # Original data: "categories": { "1": {"id": "1", "name": "Movies"} }
    # We want to preserve IDs if possible, but SQLite handles its own.
    # However, categories are referenced by Name in posts usually?
    # Let's just insert names.
    if "categories" in data:
        for cat in data["categories"].values():
            name = cat.get("name")
            if name:
                c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    
    # Posts
    # "posts": { "1": {...} }
    if "posts" in data:
        posts = data["posts"]
        # Sort by ID to insert in order
        try:
            sorted_ids = sorted(posts.keys(), key=lambda x: int(x))
        except:
            sorted_ids = posts.keys()
            
        for pid in sorted_ids:
            p = posts[pid]
            try:
                pid_int = int(pid)
                # Ensure we don't overwrite if exists (though table is empty)
                
                ptype = p.get("type", "link")
                status = p.get("status", "active")
                category = p.get("category", "Uncategorized")
                views = p.get("views", 0)
                created_at = p.get("created_at", int(time.time()))
                
                # Make sure ID is stored in the JSON blob too just in case
                p['id'] = str(pid_int) 
                
                c.execute("""INSERT INTO posts (id, type, status, category, views, created_at, data) 
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (pid_int, ptype, status, category, views, created_at, json.dumps(p, ensure_ascii=False)))
            except Exception as e:
                print(f"Failed to migrate post {pid}: {e}")
                
    conn.commit()
    print("Migration Done.")

# --- API ---

def get_post(post_id: str) -> Optional[Dict[str, Any]]:
    # 1. Fetch from DB
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT data FROM posts WHERE id = ?", (post_id,))
        row = c.fetchone()
        conn.close()
        
    if row:
        return json.loads(row['data'])
    return None

def add_post(post_data: Dict[str, Any]) -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        # Deduplication Logic
        unique_id = post_data.get("file_unique_id")
        if unique_id:
            # We must search strictly in the JSON data column
            # Since SQLite doesn't have great JSON support in all versions, we iterate or use LIKE
            # But iterating thousands of posts is slow.
            # Faster approach: Add a dedicated column or index? 
            # For now, let's use a query on 'data' column with LIKE. unique_id is long and unique.
            # A simple LIKE '%"file_unique_id": "UNIQUE_ID"%' should work.
            
            # NOTE: JSON keys order is not guaranteed, but standard dumps usually keep it? 
            # No, standard dumps don't guarantee. But file_unique_id string search is fairly safe.
            search_pattern = f'%"{unique_id}"%'
            c.execute("SELECT id FROM posts WHERE data LIKE ?", (search_pattern,))
            existing = c.fetchone()
            if existing:
                conn.close()
                return str(existing[0])

        # We let DB assign ID
        ptype = post_data.get("type", "link")
        status = post_data.get("status", "active")
        category = post_data.get("category", "Uncategorized")
        views = post_data.get("views", 0)
        created_at = post_data.get("created_at", int(time.time()))
        
        # We insert partial data first to get ID
        c.execute("""INSERT INTO posts (type, status, category, views, created_at, data) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (ptype, status, category, views, created_at, "{}"))
        
        new_id = c.lastrowid
        
        # Now update the JSON blob with the ID
        post_data['id'] = str(new_id)
        if "created_at" not in post_data: post_data['created_at'] = created_at
        if "views" not in post_data: post_data['views'] = views
        if "status" not in post_data: post_data['status'] = status
        
        c.execute("UPDATE posts SET data = ? WHERE id = ?", (json.dumps(post_data, ensure_ascii=False), new_id))
        conn.commit()
        conn.close()
        return str(new_id)

def update_post(post_id: str, updates: Dict[str, Any]):
    current = get_post(post_id)
    if not current: return
    
    current.update(updates)
    
    # Update core columns if they changed
    status = current.get("status")
    category = current.get("category")
    views = current.get("views")
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""UPDATE posts SET 
                     data = ?,
                     status = ?,
                     category = ?,
                     views = ?
                     WHERE id = ?""", 
                  (json.dumps(current, ensure_ascii=False), status, category, views, post_id))
        conn.commit()
        conn.close()

def delete_post(post_id: str, soft_delete: bool = True):
    if soft_delete:
        update_post(post_id, {"status": "deleted"})
    else:
        with lock:
            conn = get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.commit()
            conn.close()

def restore_post(post_id: str):
    update_post(post_id, {"status": "active"})

def get_all_posts() -> List[Dict[str, Any]]:
    """Returns a list of all posts (parsed JSON)."""
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT data FROM posts")
        rows = c.fetchall()
        conn.close()
    
    posts = []
    for row in rows:
        try:
            posts.append(json.loads(row['data']))
        except:
            pass
    return posts

def clone_post(post_id: str) -> Optional[str]:
    post = get_post(post_id)
    if not post: return None
    
    new_post = post.copy()
    # Remove ID so new one is generated
    if 'id' in new_post: del new_post['id']
    
    new_post["created_at"] = int(time.time())
    new_post["views"] = 0
    new_post["note"] = f"Cloned from #{post_id}"
    
    return add_post(new_post)

# --- Config / Templates ---

def save_template(name: str, content: str):
    # Old logic: templates keys "name"
    # We will store in config or separate table?
    # Old storage had "templates" dict.
    # We will use config table with prefix 'tpl_'?
    # Or strict mapping. 'templates' was a dict of {name: {name, content}}
    # Let's use config with json.
    
    # Actually, let's keep it simple.
    # The code uses `get_templates()`.
    # Let's mimic that.
    
    # We'll use a `templates` specific dict stored in `config`?
    # No, that's back to big JSON.
    # Let's assume templates are few.
    # We can store in config key="templates_json"
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'templates'")
        row = c.fetchone()
        if row:
            tpls = json.loads(row[0])
        else:
            tpls = {}
            
        tpls[name] = {"name": name, "content": content}
        
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("templates", json.dumps(tpls, ensure_ascii=False)))
        conn.commit()
        conn.close()

def get_templates():
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'templates'")
        row = c.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return {}

def get_message_template() -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'msg_template'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else INITIAL_MSG_TEMPLATE

def update_message_template(template: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("msg_template", template))
        conn.commit()
        conn.close()

def get_main_template() -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'main_template'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else INITIAL_MAIN_TEMPLATE

def update_main_template(template: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("main_template", template))
        conn.commit()
        conn.close()

def get_help_link() -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'help_link'")
        row = c.fetchone()
        conn.close()
        return row[0] if row else "https://t.me/example_tutorial"

def update_help_link(link: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("help_link", link))
        conn.commit()
        conn.close()

def get_last_news() -> Optional[str]:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'last_news'")
        row = c.fetchone()
        conn.close()
    return row[0] if row else None

def save_last_news(content: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("last_news", content))
        conn.commit()
        conn.close()

def get_auto_delete_timer() -> int:
    """Returns global auto-delete timer in SECONDS."""
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'auto_delete_timer'")
        row = c.fetchone()
        conn.close()
        
    if row:
        try:
            return int(row[0])
        except:
            pass
    return 1800 # Default 30 mins

def update_auto_delete_timer(seconds: int):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("auto_delete_timer", str(seconds)))
        conn.commit()
        conn.close()

def get_protect_content() -> bool:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'protect_content'")
        row = c.fetchone()
        conn.close()
    
    # Default is False (Off)
    if row:
        return row[0] == "1" or row[0].lower() == "true"
    return False

def get_welcome_message() -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key = 'welcome_message'")
        row = c.fetchone()
        conn.close()
    return row[0] if row else "👋 Welcome! Use a valid link to access content."

def update_welcome_message(text: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("welcome_message", text))
        conn.commit()
        conn.close()

def update_protect_content(enabled: bool):
    val = "1" if enabled else "0"
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ("protect_content", val))
        conn.commit()
        conn.close()


# --- Categories ---

def get_categories() -> Dict[str, Any]:
    # Returns formatted dict: { "1": {"id": "1", "name": "Name"}, ... }
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM categories")
        rows = c.fetchall()
        conn.close()
        
    res = {}
    for r in rows:
        sid = str(r["id"])
        res[sid] = {"id": sid, "name": r["name"]}
    return res

def add_category(name: str) -> str:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            conn.commit()
            new_id = c.lastrowid
        except sqlite3.IntegrityError:
            # Already exists?
            c.execute("SELECT id FROM categories WHERE name = ?", (name,))
            new_id = c.fetchone()[0]
        conn.close()
    return str(new_id)

def update_category(cat_id: str, name: str):
    # Need to update posts too?
    # Old logic:
    # 1. Get old name
    # 2. Update category name
    # 3. Update all posts with old name to new name
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        c.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
            
        old_name = row[0]
        
        c.execute("UPDATE categories SET name = ? WHERE id = ?", (name, cat_id))
        
        # Update posts
        # We need to update the 'category' column AND the JSON blob
        # Updating JSON blob in SQL is hard without JSON extension.
        # So we fetch all affected posts, update python dict, and save back.
        # OR just update the column and let the JSON blob get updated lazily?
        # No, `get_post` returns JSON blob. We MUST update JSON blob.
        
        c.execute("SELECT id, data FROM posts WHERE category = ?", (old_name,))
        matches = c.fetchall()
        
        for m in matches:
            pid = m["id"]
            pdata = json.loads(m["data"])
            pdata["category"] = name
            c.execute("UPDATE posts SET category = ?, data = ? WHERE id = ?", (name, json.dumps(pdata, ensure_ascii=False), pid))
            
        conn.commit()
        conn.close()

def delete_category(cat_id: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        c.execute("SELECT name FROM categories WHERE id = ?", (cat_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
            
        cat_name = row[0]
        c.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        
        # Update posts to "Uncategorized"
        c.execute("SELECT id, data FROM posts WHERE category = ?", (cat_name,))
        matches = c.fetchall()
        
        for m in matches:
            pid = m["id"]
            pdata = json.loads(m["data"])
            pdata["category"] = "Uncategorized"
            c.execute("UPDATE posts SET category = ?, data = ? WHERE id = ?", ("Uncategorized", json.dumps(pdata, ensure_ascii=False), pid))
            
        conn.commit()
        conn.close()
        
# --- New Helpers for Scalability ---

def get_latest_post_id() -> int:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT MAX(id) FROM posts")
        res = c.fetchone()[0]
        conn.close()
    return res if res else 0

def get_posts_paginated(page: int = 0, page_size: int = 10, category_filter: str = "All") -> List[Tuple[int, Dict[str, Any]]]:
    # Returns list of (id, post_dict)
    offset = page * page_size
    
    query = "SELECT id, data FROM posts WHERE status != 'deleted'"
    params = []
    
    if category_filter != "All":
        query += " AND category = ?"
        params.append(category_filter)
        
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([page_size, offset])
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute(query, tuple(params))
        rows = c.fetchall()
        conn.close()
        
    results = []
    for r in rows:
        results.append((r["id"], json.loads(r["data"])))
    return results

def get_posts_count(category_filter: str = "All") -> int:
    query = "SELECT COUNT(*) FROM posts WHERE status != 'deleted'"
    params = []
    
    if category_filter != "All":
        query += " AND category = ?"
        params.append(category_filter)
        
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute(query, tuple(params))
        count = c.fetchone()[0]
        conn.close()
    return count

def get_post_stats() -> Dict[str, Any]:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        # Total Posts
        c.execute("SELECT COUNT(*) FROM posts")
        total_posts = c.fetchone()[0]
        
        # Active
        c.execute("SELECT COUNT(*) FROM posts WHERE status = 'active'")
        active_posts = c.fetchone()[0]
        
        # Total Views
        c.execute("SELECT SUM(views) FROM posts")
        total_views = c.fetchone()[0] or 0
        
        # Top Categories
        c.execute("SELECT category, COUNT(*) as cnt FROM posts GROUP BY category ORDER BY cnt DESC LIMIT 3")
        top_cats = c.fetchall()
        
        # Top Posts by Views
        # Note: 'views' column is updated on view.
        c.execute("SELECT id, views, category FROM posts ORDER BY views DESC LIMIT 5")
        top_posts = []
        for r in c.fetchall():
            top_posts.append({"id": r["id"], "views": r["views"], "category": r["category"]})
            
        conn.close()
        
    return {
        "total_posts": total_posts,
        "active_posts": active_posts,
        "total_views": total_views,
        "top_categories": [(r["category"], r["cnt"]) for r in top_cats],
        "top_posts": top_posts
    }

def search_posts(query: str, limit: int = 10) -> List[Tuple[int, Dict[str, Any]]]:
    # Search logic:
    # If digit: Exact ID match
    # Else: LIKE query on data (but data is JSON string, so LIKE %query% works for text inside JSON)
    # Ideally FTS enabled, but simple LIKE is better than loading all.
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        if query.isdigit():
            c.execute("SELECT id, data FROM posts WHERE id = ?", (int(query),))
        else:
            # We search in raw JSON string. It's case insensitive usually?
            # SQLite LIKE is case-insensitive for ASCII.
            c.execute("SELECT id, data FROM posts WHERE data LIKE ? LIMIT ?", (f"%{query}%", limit))
            
        rows = c.fetchall()
        conn.close()
        
    results = []
    for r in rows:
        results.append((r["id"], json.loads(r["data"])))
    return results

def get_pending_scheduled_posts() -> List[Tuple[int, Dict[str, Any]]]:
    
    with lock:
        conn = get_connection()
        c = conn.cursor()
        # "is_scheduled": true  (ignoring spacing issues in json text by using LIKE or proper json extract if available)
        # Simple LIKE query is safest without json extension dependence
        c.execute("SELECT id, data FROM posts WHERE data LIKE '%\"is_scheduled\": true%'")
        rows = c.fetchall()
        conn.close()
    
    results = []
    for r in rows:
        results.append((r["id"], json.loads(r["data"])))
    return results

def get_all_posts() -> Dict[str, Any]:
    # DEPRECATED: For backward compatibility only.
    # WARNING: Heavy.
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, data FROM posts")
        rows = c.fetchall()
        conn.close()
        
    res = {}
    for r in rows:
        res[str(r['id'])] = json.loads(r['data'])
    return res

# Initialize on module load
init_db()

# --- SMART FEATURES SUPPORT ---

def init_db_extras():
    """Called to ensure new tables exist"""
    conn = get_connection()
    c = conn.cursor()
    
    # Users Table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        joined_at INTEGER,
        is_banned BOOLEAN DEFAULT 0
    )""")
    
    # Force Subscribe Channels
    c.execute("""CREATE TABLE IF NOT EXISTS force_sub (
        channel_id TEXT PRIMARY KEY,
        invite_link TEXT,
        title TEXT
    )""")
    
    conn.commit()
    conn.close()

# Run extras init immediately
init_db_extras()

def add_user(user_id: int, username: str = None):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT OR IGNORE INTO users (user_id, username, joined_at) VALUES (?, ?, ?)", 
                      (user_id, username, int(time.time())))
            # Update username if changed?
            if username:
                c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()
        except Exception as e:
            print(f"Error adding user: {e}")
        conn.close()

def get_all_users_count() -> int:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        res = c.fetchone()[0]
        conn.close()
    return res

def get_all_users_iter():
    """Generator to yield users for broadcasting without loading all in RAM"""
    # Use pagination
    limit = 100
    offset = 0
    while True:
        with lock:
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT user_id FROM users LIMIT ? OFFSET ?", (limit, offset))
            rows = c.fetchall()
            conn.close()
        
        if not rows:
            break
            
        for r in rows:
            yield r[0]
        
        offset += limit

# -- Ban System --
def ban_user(user_id: int):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        # Insert if not exists, then update
        c.execute("INSERT OR IGNORE INTO users (user_id, joined_at) VALUES (?, ?)", (user_id, int(time.time())))
        c.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def unban_user(user_id: int):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def is_banned(user_id: int) -> bool:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
    return True if row and row[0] else False

# -- Force Sub --
def add_force_sub(channel_id: str, invite_link: str, title: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO force_sub (channel_id, invite_link, title) VALUES (?, ?, ?)", 
                  (str(channel_id), invite_link, title))
        conn.commit()
        conn.close()

def remove_force_sub(channel_id: str):
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM force_sub WHERE channel_id = ?", (str(channel_id),))
        conn.commit()
        conn.close()

def get_force_subs() -> List[Dict[str, str]]:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM force_sub")
        rows = c.fetchall()
        conn.close()
    
    return [{"id": r["channel_id"], "link": r["invite_link"], "title": r["title"]} for r in rows]

# -- Advanced Search --
def search_posts_advanced(query: str, type_filter: str = None, status_filter: str = None, limit: int = 20) -> List[Tuple[int, Dict[str, Any]]]:
    with lock:
        conn = get_connection()
        c = conn.cursor()
        
        sql = "SELECT id, data FROM posts WHERE 1=1"
        params = []
        
        if query:
            if query.isdigit():
                sql += " AND id = ?"
                params.append(int(query))
            else:
                sql += " AND data LIKE ?"
                params.append(f"%{query}%")
                
        if type_filter and type_filter != "All":
            sql += " AND type = ?"
            # JSON extraction via LIKE is hard for fields.
            # But wait, we have columns 'type', 'status', 'category'!
            # We created them in init_db line 60.
            params.append(type_filter.lower())
            
        if status_filter and status_filter != "All":
             st = status_filter.lower()
             if st == "active":
                 sql += " AND status = 'active'"
             elif st == "disabled":
                 sql += " AND (status = 'disabled' OR status = 'deleted')"
            
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        c.execute(sql, tuple(params))
        rows = c.fetchall()
        conn.close()
        
    results = []
    for r in rows:
        results.append((r["id"], json.loads(r["data"])))
    return results
def delete_all_posts():
    """Deletes ALL posts from the database."""
    with lock:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM posts")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting all posts: {e}")
            return False
