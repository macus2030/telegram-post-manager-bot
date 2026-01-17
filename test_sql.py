import storage_sql
import os

print(f"DB Exists: {os.path.exists('bot.db')}")

# Check migration
posts = storage_sql.get_all_posts()
print(f"Total Posts in DB: {len(posts)}")

cats = storage_sql.get_categories()
print(f"Categories in DB: {cats}")

print("Testing Add Post...")
new_id = storage_sql.add_post({"caption": "Test SQL"})
print(f"Added Post #{new_id}")

print("Testing Get Post...")
p = storage_sql.get_post(new_id)
print(f"Retrieved: {p}")

print("Testing Update Post...")
storage_sql.update_post(new_id, {"views": 99})
p = storage_sql.get_post(new_id)
print(f"Updated Views: {p['views']}")
