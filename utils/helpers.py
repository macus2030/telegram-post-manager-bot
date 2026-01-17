import asyncio
from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import telegram.error

async def send_temp_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, delay: int = 4):
    """Send a message that auto-deletes after 'delay' seconds."""
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
        asyncio.create_task(delete_message_delayed(msg, delay))
    except Exception as e:
        print(f"Error sending temp message: {e}")

async def delete_message_delayed(message: Message, delay: int):
    """Wait for delay and then delete the message."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass

async def show_loading(update: Update, text: str = "⏳ Processing...") -> Message:
    """Send a loading message to be edited later."""
    if update.callback_query:
        # If callback, try to edit current message or answer callback
        await update.callback_query.answer()
        return await update.callback_query.edit_message_text(text=text)
    elif update.message:
        return await update.message.reply_text(text=text)
    return None

def escape_markdown_v2(text: str) -> str:
    """Helper to escape markdown v2 special chars if needed."""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{c}' if c in special_chars else c for c in text)

def check_admin(user_id: int) -> bool:
    """Check if user is the admin."""
    from config import ADMIN_ID
    return user_id == ADMIN_ID
    
def validate_link(text: str) -> str | None:
    """Validate and format a link. Returns None if invalid."""
    text = text.strip()
    
    # Needs at least one dot to be a domain/link
    if "." not in text:
        return None
        
    # Auto-add https:// if missing
    if not (text.startswith("http://") or text.startswith("https://")):
        text = f"https://{text}"
        
    return text
