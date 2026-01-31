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

async def send_temp_photo(context: ContextTypes.DEFAULT_TYPE, chat_id: int, photo_id: str, caption: str = "", delay: int = 10, protect_content: bool = True):
    """Send a photo that auto-deletes after 'delay' seconds."""
    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id, 
            photo=photo_id, 
            caption=caption, 
            parse_mode=ParseMode.HTML,
            protect_content=protect_content
        )
        asyncio.create_task(delete_message_delayed(msg, delay))
    except Exception as e:
        print(f"Error sending temp photo: {e}")

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

async def check_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> list:
    """Check if user is member of Required Channels. Returns list of missing channel info dicts."""
    from config import MAIN_CHANNEL_ID
    from storage import get_force_subs
    
    missing = []
    
    # 1. Main Channel (Legacy/Env)
    if MAIN_CHANNEL_ID:
        try:
            member = await context.bot.get_chat_member(chat_id=MAIN_CHANNEL_ID, user_id=user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                # Get Link
                try:
                     chat = await context.bot.get_chat(MAIN_CHANNEL_ID)
                     link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else "https://t.me/"
                     title = chat.title or "Main Channel"
                except:
                     link = "https://t.me/"
                     title = "Main Channel"
                missing.append({"title": title, "link": link})
        except Exception as e:
            print(f"Error checking main channel: {e}")
            # If error (e.g. bot kicked), we usually fail open or closed. 
            # Let's fail open (assume joined) to avoid blocking users if bot breaks.
            pass
            
    # 2. Dynamic Channels
    force_subs = get_force_subs()
    for ch in force_subs:
        try:
            member = await context.bot.get_chat_member(chat_id=ch['id'], user_id=user_id)
            if member.status not in ['creator', 'administrator', 'member']:
                missing.append({"title": ch['title'], "link": ch['link']})
        except telegram.error.BadRequest:
            # Bot likely not in channel
            pass
        except Exception as e:
            print(f"Error checking fs channel {ch['id']}: {e}")
            
    return missing

    return missing

def get_post_timer(post: dict) -> int:
    """Get auto-delete timer for specific post or default."""
    from storage import get_auto_delete_timer
    
    # Check if post has override
    if post.get("auto_delete_timer"):
         minutes = int(post.get("auto_delete_timer"))
         if minutes > 0: # Only if positive, 0 might mean default in future? But "Set 0 to use Global Default" -> so 0 in DB means None or ignored. Post creation sets auto_delete_timer to None or deletes key if 0. 
             # admin.py stores it as: "auto_delete_timer": data.get('auto_delete_timer') where data has it if input was not 0.
             # If user entered 0, it reset to default (deleted key).
             # So if key exists, it's an override.
             return minutes * 60
         
    return get_auto_delete_timer()

# --- Obfuscation ---
import base64
OBFUSCATION_KEY = 7439121 

def encode_payload(post_id: int) -> str:
    """XOR + Base64 Encode post ID."""
    try:
        val = int(post_id) ^ OBFUSCATION_KEY
        return base64.urlsafe_b64encode(str(val).encode()).decode().rstrip("=")
    except:
        return str(post_id)

def decode_payload(payload: str) -> int | None:
    """Decode post ID. Returns None if invalid."""
    try:
        # Strict Mode: No backward compatibility for plain integers
        
        pad = len(payload) % 4
        if pad: payload += "=" * (4 - pad)
        s = base64.urlsafe_b64decode(payload.encode()).decode()
        return int(s) ^ OBFUSCATION_KEY
    except:
        return None
