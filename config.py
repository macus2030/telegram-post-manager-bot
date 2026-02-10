import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
MAIN_CHANNEL_ID = os.getenv("MAIN_CHANNEL_ID")
BACKUP_CHANNEL_ID = os.getenv("BACKUP_CHANNEL_ID")

# Defaults
AUTO_DELETE_SECONDS = 1800  # 30 minutes
HOW_TO_OPEN_LINK = "https://t.me/example_tutorial"
