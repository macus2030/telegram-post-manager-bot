import json
import os
import threading
import time
from typing import Dict, Any, Optional

DATA_FILE = "data.json"
lock = threading.Lock()

# Initial structure
INITIAL_DATA = {
    "posts": {},
    "templates": {},
    "categories": {},
    "msg_template": """LN Post : {post_id}

{caption}

📂 Category: {category}
⏳ This message will auto-delete in {time} mins.

Download/Watch Link👇🏻 
{link}

How to Open 
{how_to_open_link}""",
    "main_template": """{news}

ISKO IGNORE KARO, VIDEOS KI LINK NICHE HAI..😉
.
Post - LN{post_id}
{short_link}

How to Use Telegram Bot?
{how_to_open_link}"""
}

def load_data() -> Dict[str, Any]:
    """Load data from JSON file or return initial structure if not exists."""
    if not os.path.exists(DATA_FILE):
        # Initialize default categories if creating new
        INITIAL_DATA["categories"] = {
            "1": {"id": "1", "name": "Movies"},
            "2": {"id": "2", "name": "Series"},
            "3": {"id": "3", "name": "Other"}
        }
        save_data(INITIAL_DATA)
        return INITIAL_DATA
    
    with lock:
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure categories exist in old data
                if "categories" not in data:
                    data["categories"] = {
                         "1": {"id": "1", "name": "Movies"},
                         "2": {"id": "2", "name": "Series"},
                         "3": {"id": "3", "name": "Other"}
                    }
                    save_data(data)
                return data
        except (json.JSONDecodeError, FileNotFoundError):
            return INITIAL_DATA

def save_data(data: Dict[str, Any]):
    """Save data to JSON file with thread safety."""
    with lock:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

def get_post(post_id: str) -> Optional[Dict[str, Any]]:
    data = load_data()
    return data["posts"].get(str(post_id))

def add_post(post_data: Dict[str, Any]) -> str:
    """Add a new post and return its ID."""
    data = load_data()
    # Auto-increment ID
    current_ids = [int(k) for k in data["posts"].keys()]
    new_id = str(max(current_ids) + 1 if current_ids else 1)
    
    # Add timestamps defaults
    if "created_at" not in post_data:
        post_data["created_at"] = int(time.time())
    if "views" not in post_data:
        post_data["views"] = 0
    if "status" not in post_data:
        post_data["status"] = "active"
        
    data["posts"][new_id] = post_data
    save_data(data)
    return new_id

def update_post(post_id: str, updates: Dict[str, Any]):
    data = load_data()
    if str(post_id) in data["posts"]:
        data["posts"][str(post_id)].update(updates)
        save_data(data)

def delete_post(post_id: str, soft_delete: bool = True):
    data = load_data()
    if str(post_id) in data["posts"]:
        if soft_delete:
            data["posts"][str(post_id)]["status"] = "deleted"
        else:
            del data["posts"][str(post_id)]
        save_data(data)

def restore_post(post_id: str):
    data = load_data()
    if str(post_id) in data["posts"]:
        # Restore to active or draft? Let's check previous state or default to active.
        # Actually safest is active or the previous valid status.
        # But for now 'active' is fine as we only delete active/disabled posts usually.
        data["posts"][str(post_id)]["status"] = "active"
        save_data(data)

def clone_post(post_id: str) -> Optional[str]:
    """Duplicate a post and return the new ID."""
    post = get_post(post_id)
    if not post:
        return None
    
    new_post = post.copy()
    new_post["created_at"] = int(time.time())
    new_post["views"] = 0
    new_post["note"] = f"Cloned from #{post_id}"
    
    return add_post(new_post)

def get_all_posts():
    return load_data()["posts"]

# Template handlers
def save_template(name: str, content: str):
    data = load_data()
    data["templates"][name] = {"name": name, "content": content}
    save_data(data)


def get_templates():
    return load_data()["templates"]

def get_message_template() -> str:
    data = load_data()
    return data.get("msg_template", INITIAL_DATA["msg_template"])

def update_message_template(template: str):
    data = load_data()
    data["msg_template"] = template
    save_data(data)

def get_help_link() -> str:
    data = load_data()
    # Default fallback
    return data.get("help_link", "https://t.me/example_tutorial")

def update_help_link(link: str):
    data = load_data()
    data["help_link"] = link
    save_data(data)

def get_main_template() -> str:
    data = load_data()
    return data.get("main_template", INITIAL_DATA["main_template"])

def update_main_template(template: str):
    data = load_data()
    data["main_template"] = template
    save_data(data)

# Category Handlers
def get_categories() -> Dict[str, Any]:
    return load_data()["categories"]

def get_category(cat_id: str) -> Optional[Dict[str, Any]]:
    return get_categories().get(str(cat_id))

def add_category(name: str) -> str:
    data = load_data()
    current_ids = [int(k) for k in data["categories"].keys()]
    new_id = str(max(current_ids) + 1 if current_ids else 1)
    
    data["categories"][new_id] = {
        "id": new_id, 
        "name": name
    }
    save_data(data)
    return new_id

def update_category(cat_id: str, name: str):
    data = load_data()
    if str(cat_id) in data["categories"]:
        old_name = data["categories"][str(cat_id)]["name"]
        data["categories"][str(cat_id)]["name"] = name
        
        # Update all posts with this category
        for post in data["posts"].values():
            if post.get("category") == old_name:
                post["category"] = name
                
        save_data(data)

def delete_category(cat_id: str):
    data = load_data()
    if str(cat_id) in data["categories"]:
        cat_name = data["categories"][str(cat_id)]["name"]
        del data["categories"][str(cat_id)]
        
        # Update posts to Uncategorized
        for post in data["posts"].values():
            if post.get("category") == cat_name:
                post["category"] = "Uncategorized"
                
        save_data(data)
