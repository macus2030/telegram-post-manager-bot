from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode, ChatAction
from storage import get_post, update_post, is_banned, add_user, get_protect_content

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
        # Normal User /start without args
        from storage import get_welcome_message
        await update.message.reply_text(get_welcome_message())
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
        # Allow Admin to view (with warning)
        if check_admin(user.id):
            await update.message.reply_text(
                f"⚠️ **Admin Warning**: This post is currently `{post.get('status')}`.\n"
                "Users cannot see this.",
                parse_mode=ParseMode.MARKDOWN
            )
            # Proceed to show content...
        else:
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

    import html
    variables = {
        "post_id": post_id,
        "channel_post_id": str(post.get("channel_message_id", "0")),
        "category": html.escape(str(post.get("category", "Uncategorized"))),
        "time": int(timer_seconds/60),
        "time_sec": timer_seconds,
        "link": html.escape(str(post_link)),
        "how_to_open_link": html.escape(str(get_help_link()))
    }
    
    # Pre-format caption to replace internal variables like {link}
    raw_caption = post.get("caption", "")
    try:
        # We assume caption might use same variables except 'caption'
        processed_caption = raw_caption.format(**variables)
    except:
        # If formatting fails (e.g. invalid keys), keep raw
        processed_caption = raw_caption
        
    variables["caption"] = processed_caption
    
    # 4. Modify Template for File Type (Step 3 Requirement)
    post_type = post.get("type", "link")
    if post_type == "file":
         # Remove Link Section
         # We expect the template to have "Download / Watch Link... {link}"
         # A regex replace is safest to cover variations if user edited it
         template = re.sub(r"(?i)Download / Watch Link.*\{link\}.*(\n|$)", "", template, flags=re.DOTALL)
         # Clean up double newlines potentially left behind
         template = re.sub(r"\n\s*\n\s*\n", "\n\n", template)
         
         # Add Prefix
         template = "📦 File : RAR / ZIP\n\n" + template.strip()

    try:
        final_caption = template.format(**variables)
    except KeyError as e:
        final_caption = f"⚠ Template Error: Missing {e}\n\n" + post.get("caption", "")
    except Exception as e:
         final_caption = post.get("caption", "")

    # 5. Send Content
    try:
        sent_msg = None
        # post_type already defined above
        
        # Protection Logic
        is_protected = get_protect_content()
        
        # Button Logic (Password)
        reply_markup = None
        if post.get("password"):
             reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Password", callback_data=f"pass_{post_id}")]])
        
        if post_type == "file":
             file_id = post.get("file_id")
             file_type = post.get("file_type", "document")
             
             if file_type == "document":
                 sent_msg = await update.message.reply_document(document=file_id, caption=final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
             elif file_type == "video":
                 sent_msg = await update.message.reply_video(video=file_id, caption=final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
             elif file_type == "photo":
                 sent_msg = await update.message.reply_photo(photo=file_id, caption=final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
             elif file_type == "audio":
                 sent_msg = await update.message.reply_audio(audio=file_id, caption=final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
                 
        else: # Link type
            sent_msg = await update.message.reply_text(final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
            
        # 5. Schedule Auto-Delete
        if sent_msg:
             context.job_queue.run_once(auto_delete_job, timer_seconds, chat_id=update.effective_chat.id, data={'msg_id': sent_msg.message_id, 'timer': timer_seconds})
            
    except Exception as e:
        traceback.print_exc()
        print(f"Error sending content: {e}")
        await update.message.reply_text("⚠ Error retrieving content. Please try again.")

async def auto_delete_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to delete the message."""
    job = context.job
    data = job.data
    
    msg_id = None
    timer = None
    
    # Backward compatibility
    if isinstance(data, int):
        msg_id = data
    elif isinstance(data, dict):
        msg_id = data.get('msg_id')
        timer = data.get('timer')
        
    if msg_id:
        try:
            await context.bot.delete_message(chat_id=job.chat_id, message_id=msg_id)
            
            # Send Notification if timer is known
            if timer:
                mins = timer / 60
                if mins >= 1:
                    time_str = f"{int(mins)} mins"
                else:
                    time_str = f"{timer} seconds"
                    
                await context.bot.send_message(
                    chat_id=job.chat_id, 
                    text=f"{time_str} is completed, and your file has been successfully deleted. ✅",
                    parse_mode=ParseMode.MARKDOWN
                )
                
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

async def handle_password_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    post_id = query.data.split("_")[1]
    
    post = get_post(post_id)
    if not post or not post.get("password"):
        await query.answer("❌ No password found.", show_alert=True)
        return
        
    password = post.get("password")
    
    # Send as hidden text (or alert?) user asked for "message password copyed" and "directly copy"
    # Alert is best for "copy"? No, Telegram alerts don't copy to clipboard easily.
    # Sending a message `code` allows tap to copy.
    # User Request: "currunt password of file or link directly copu and messeg password copyed"
    # Implementation: Send a ephemeral message with monospaced password.
    
    await query.answer("✅ Password Sent!", show_alert=False)
    await query.message.reply_text(
        f"🔑 Password:\n<code>{password}</code>", 
        parse_mode=ParseMode.HTML
    )

