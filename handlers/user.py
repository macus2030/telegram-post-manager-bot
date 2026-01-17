from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
from storage import get_post, update_post
from config import AUTO_DELETE_SECONDS
from utils.helpers import send_temp_message, check_admin
from utils.helpers import send_temp_message, check_admin
import asyncio
import traceback

async def start_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command. Check for deep link parameters."""
    args = context.args
    
    if not args:
        # Check if Admin
        if check_admin(update.effective_user.id):
             from handlers.admin import admin_dashboard
             await admin_dashboard(update, context)
             return
             
        # Normal User /start without args
        await update.message.reply_text("👋 Welcome! Use a valid link to access content.")
        return

    post_id = args[0]
    post = get_post(post_id)
    
    # 1. Validate Post
    if not post:
        await update.message.reply_text("❌ This link is invalid or has expired.")
        return
        
    if post.get("status") != "active":
        await update.message.reply_text("❌ This post is currently unavailable.")
        return
        
    # TODO: Check expires_at logic if implemented
    
    # 2. Increment View Counter
    current_views = post.get("views", 0)
    update_post(post_id, {"views": current_views + 1})
    
    # 3. Prepare Template Variables
    from storage import get_message_template, get_help_link
    from config import AUTO_DELETE_SECONDS
    import re

    template = get_message_template()
    post_link = post.get("link", "")
    
    # Check if link is missing or empty
    if not post_link: 
        post_link = ""
        # Magic: If link is empty, try to remove the specific header line directly from the template
        # ensuring we don't leave a dangling header.
        # This matches lines containing "Download/Watch Link" or "Link👇" case insensitive
        template = re.sub(r"(?i)^.*(Download/Watch Link|Link👇).*$\n?", "", template, flags=re.MULTILINE)

    variables = {
        "post_id": post_id,
        "caption": post.get("caption", ""),
        "category": post.get("category", "Uncategorized"),
        "time": int(AUTO_DELETE_SECONDS/60),
        "link": post_link,
        "how_to_open_link": get_help_link()


    }
    
    # Safe format (handles missing keys in template gracefully if we used strict formatting, 
    # but here we use standard .format(). If user puts invalid key, it might crash. 
    # Let's wrap in safe format or try/except).
    try:
        final_caption = template.format(**variables)
    except KeyError as e:
        # Fallback if user messed up template variables
        final_caption = f"⚠ Template Error: Missing {e}\n\n" + post.get("caption", "")
    except Exception as e:
         final_caption = post.get("caption", "")

    # 4. Send Content
    try:
        sent_msg = None
        post_type = post.get("type", "link")
        
        if post_type == "file":
             file_id = post.get("file_id")
             file_type = post.get("file_type", "document")
             
             # Telegram caption limit is 1024 chars. If template is long, we might need to send text separately?
             # For now, assume it fits or text post fallback.
             if len(final_caption) > 1024:
                 # Send file then text? Or just shorten?
                 # Let's send file with short caption and then full info? No, user wants one message.
                 # Just use reply_message if file type supports it.
                 pass

             if file_type == "document":
                 sent_msg = await update.message.reply_document(document=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "video":
                 sent_msg = await update.message.reply_video(video=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "photo":
                 sent_msg = await update.message.reply_photo(photo=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "audio":
                 sent_msg = await update.message.reply_audio(audio=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
                 
        else: # Link type
            # HTML escape logic not strictly enforced here but recommended if caption has weird chars.
            # Assuming user inputs safe text or we could use html.escape(final_caption)
            sent_msg = await update.message.reply_text(final_caption, parse_mode=ParseMode.HTML)
            
        # 5. Schedule Auto-Delete
        if sent_msg:
             context.job_queue.run_once(auto_delete_job, AUTO_DELETE_SECONDS, chat_id=update.effective_chat.id, data=sent_msg.message_id)
            
    except Exception as e:
        traceback.print_exc()
        print(f"Error sending content: {e}")
        await update.message.reply_text("⚠ Error retrieving content. Please try again.")

async def auto_delete_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to delete the message."""
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.chat_id, message_id=job.data)
    except Exception as e:
        print(f"Auto-delete failed: {e}")
