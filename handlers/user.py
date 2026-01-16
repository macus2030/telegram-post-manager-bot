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
    
    # 3. Send Content
    try:
        sent_msg = None
        # Use HTML for better robustness with URLs
        footer = f"\n\n⏳ <i>This message will auto-delete in {int(AUTO_DELETE_SECONDS/60)} mins.</i>"
        caption = (post.get('caption', '') + footer)
        
        post_type = post.get("type", "link")
        
        if post_type == "file":
             file_id = post.get("file_id")
             file_type = post.get("file_type", "document")
             
             if file_type == "document":
                 sent_msg = await update.message.reply_document(document=file_id, caption=caption, parse_mode=ParseMode.HTML)
             elif file_type == "video":
                 sent_msg = await update.message.reply_video(video=file_id, caption=caption, parse_mode=ParseMode.HTML)
             elif file_type == "photo":
                 sent_msg = await update.message.reply_photo(photo=file_id, caption=caption, parse_mode=ParseMode.HTML)
             elif file_type == "audio":
                 sent_msg = await update.message.reply_audio(audio=file_id, caption=caption, parse_mode=ParseMode.HTML)
                 
        else: # Link type
            link = post.get("link", "")
            # HTML escape logic if needed, but usually URLs are fine in HTML unless they contain < >
            text = f"{caption}\n\n🔗 {link}"
            sent_msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            
        # 4. Schedule Auto-Delete
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
