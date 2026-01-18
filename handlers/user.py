from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode
from storage import get_post, update_post, is_banned, add_user
from config import AUTO_DELETE_SECONDS
from utils.helpers import send_temp_message, check_admin, check_membership, get_post_timer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio
import traceback

async def start_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command. Check for deep link parameters."""
    user = update.effective_user
    
    # 1. User Management (Feature)
    # Track user
    add_user(user.id, user.username)
    
    # Check Ban
    if is_banned(user.id):
        # Optional: Send ban message?
        return # Ignore banned users
    
    args = context.args
    
    if not args:
        # Check if Admin
        if check_admin(user.id):
             from handlers.admin import admin_dashboard
             await admin_dashboard(update, context)
             return
             
        # Normal User /start without args
        await update.message.reply_text("👋 Welcome! Use a valid link to access content.")
        return

    raw_arg = args[0]
    from utils.helpers import decode_payload
    decoded_id = decode_payload(raw_arg)
    
    if decoded_id is None:
        await update.message.reply_text("❌ Invalid Link.")
        return
        
    post_id = str(decoded_id)
    
    # Check Force Subscribe (Feature)
    missing_channels = await check_membership(user.id, context)
    
    if missing_channels:
        # Build UI
        kb = []
        for ch in missing_channels:
            kb.append([InlineKeyboardButton(f"📢 Join {ch['title']}", url=ch['link'])])
            
        # Use raw_arg (encoded) in callback to keep it hidden
        kb.append([InlineKeyboardButton("🔄 Try Again", callback_data=f"check_sub_{raw_arg}")])
        
        await update.message.reply_text(
            "⚠️ **Access Denied**\n\n"
            "You must join our channels to access this content.\n"
            "Please join below and click 'Try Again'.",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )
        return

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
    import re

    template = get_message_template()
    post_link = post.get("link", "")
    
    # Check if link is missing or empty
    if not post_link: 
        post_link = ""
        template = re.sub(r"(?i)^.*(Download/Watch Link|Link👇).*$\n?", "", template, flags=re.MULTILINE)

    # Determine Timer (Feature)
    timer_seconds = get_post_timer(post)

    variables = {
        "post_id": post_id,
        "caption": post.get("caption", ""),
        "category": post.get("category", "Uncategorized"),
        "time": int(timer_seconds/60),
        "time_sec": timer_seconds,
        "link": post_link,
        "how_to_open_link": get_help_link()
    }
    
    try:
        final_caption = template.format(**variables)
    except KeyError as e:
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
             
             if file_type == "document":
                 sent_msg = await update.message.reply_document(document=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "video":
                 sent_msg = await update.message.reply_video(video=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "photo":
                 sent_msg = await update.message.reply_photo(photo=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
             elif file_type == "audio":
                 sent_msg = await update.message.reply_audio(audio=file_id, caption=final_caption, parse_mode=ParseMode.HTML)
                 
        else: # Link type
            sent_msg = await update.message.reply_text(final_caption, parse_mode=ParseMode.HTML)
            
        # 5. Schedule Auto-Delete
        if sent_msg:
             context.job_queue.run_once(auto_delete_job, timer_seconds, chat_id=update.effective_chat.id, data=sent_msg.message_id)
            
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
        pass

async def handle_not_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    post_id = data.replace("check_sub_", "")
    
    # Re-check (returns list)
    missing = await check_membership(update.effective_user.id, context)
    
    if not missing:
        # Success!
        await query.delete_message()
        # Patch message object to allow reply
        update.message = query.message
        context.args = [post_id]
        await start_user(update, context)
    else:
        await query.answer("❌ You haven't joined all channels!", show_alert=True)
        # We could update the buttons if the list changed (e.g. joined 1 of 2), but static list is fine for now.
