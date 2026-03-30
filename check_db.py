import sqlite3
import json
conn = sqlite3.connect('bot.db')
c = conn.cursor()
c.execute("SELECT value FROM config WHERE key='news_images'")
row = c.fetchone()
if row:
    images = json.loads(row[0])
    print(f'Total images: {len(images)}')
    for img in images[-5:]:
        print(img)
else:
    print('No images found')
