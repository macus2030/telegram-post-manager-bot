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
    
    # Check for Verified Prefix (Bypass Shortener)
    is_verified = False
    if raw_arg.startswith("get_"):
        is_verified = True
        raw_arg = raw_arg[4:] # Remove "get_"
        
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
            
        # Use raw_arg (encoded) in callback to keep it hidden, verify prefix is preserved if needed?
        # If user clicked "get_", we want to preserve "get_" so they get content after joining.
        callback_arg = f"get_{raw_arg}" if is_verified else raw_arg
        kb.append([InlineKeyboardButton("🔄 Try Again", callback_data=f"check_sub_{callback_arg}")])
        
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
    
    # Check if post was shared via Main Channel Post feature
    # If so, use the shortened link from that flow instead of the original link
    if post.get("main_channel_short_link"):
        post_link = post.get("main_channel_short_link", "")
    else:
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
    
    # CLEANUP: Remove legacy text burned into caption (Dynamic Fix)
    try:
        # Remove "Post: 123" line
        raw_caption = re.sub(r"(?i)^Post\s*:\s*\d+\s*\n?", "", raw_caption, flags=re.MULTILINE)
        # Remove "(Password Protected 🔐)" line
        raw_caption = re.sub(r"(?i)^\(Password Protected 🔐\)\s*\n?", "", raw_caption, flags=re.MULTILINE)
        raw_caption = raw_caption.strip()
    except Exception as e:
        print(f"Error cleaning caption: {e}")

    try:
        # We assume caption might use same variables except 'caption'
        processed_caption = raw_caption.format(**variables)
    except:
        # If formatting fails (e.g. invalid keys), keep raw
        processed_caption = raw_caption
        
    variables["caption"] = processed_caption
    
    # Add aliases for new template variable names (backward compatibility)
    variables["content_text"] = processed_caption  # Alias for {content_text}
    variables["short_link"] = html.escape(str(post_link))  # Alias for {short_link}
    
    # 4. Check if Main Channel Short Link exists (CRITICAL LOGIC)
    # CASE 1: If shortened link exists → Send TEXT ONLY (no file attachment)
    # CASE 2: If no shortened link → Send actual file/content
    
    # DEBUG: Log the value
    main_channel_link_value = post.get("main_channel_short_link")
    print(f"DEBUG: Post #{post_id} main_channel_short_link = {main_channel_link_value}")
    
    has_main_channel_link = bool(main_channel_link_value)
    post_type = post.get("type", "link")
    
    # Prepare template based on case
    # IF VERIFIED (user came from shortener), treat as Case 2 (Send File)
    
    # --- INFINITE LOOP FIX ---
    # Check if the "Short Link" is actually pointing back to this bot with the same start param
    # This prevents users from creating a loop by carrying the start param in the short link
    is_loop_detected = False
    if has_main_channel_link:
        # Simple check: Does the link contain our username?
        # Note: This is an approximation. A perfect check requires expanding short URLs which is slow.
        # We rely on text matching.
        bot_username = context.bot.username
        if bot_username and bot_username.lower() in main_channel_link_value.lower():
             # If it also contains the start param (raw_arg), it's likely a loop
             if f"start={raw_arg}" in main_channel_link_value or f"start={post_id}" in main_channel_link_value:
                 is_loop_detected = True
                 import logging
                 logging.warning(f"[WARN] ShortLinkLoopDetected | post_id={post_id} | user_id={user.id} | raw_arg={raw_arg}")

    if has_main_channel_link and not is_verified and not is_loop_detected:
        # CASE 1: Main Channel Short Link exists AND Not Verified
        # Always send as text message, never attach file
        # This allows for monetization and copyright protection
        force_text_only = True
        
        # Use the standard template with links
        pass  # Keep template as is
        
    else:
        # CASE 2: No Main Channel Short Link OR Verified
        # Send actual file/content as normal
        force_text_only = False
        
    # Modify Template for File Type (Step 3 Requirement)
    # Apply this WHENEVER we are sending the file (force_text_only is False)
    if not force_text_only and post_type == "file":
             # Remove Link Section
             # Handle both {link} and {short_link} for backward compatibility
             # Matches "Download / Watch Link" followed by link variables
             template = re.sub(r"(?i)Download / Watch Link.*\{(short_)?link\}.*(\n|$)", "", template, flags=re.DOTALL)
             # Clean up double newlines potentially left behind
             template = re.sub(r"\n\s*\n\s*\n", "\n\n", template)
             
             # Add Prefix
             template = "\n\n" + template.strip()

    try:
        final_caption = template.format(**variables)
    except KeyError as e:
        final_caption = f"⚠ Template Error: Missing {e}\n\n" + post.get("caption", "")
    except Exception as e:
         final_caption = post.get("caption", "")

    # 5. Send Content
    try:
        sent_msg = None
        
        # Protection Logic
        is_protected = get_protect_content()
        
        # CASE 1: Main Channel Short Link exists AND Not Verified → TEXT ONLY (NO PASSWORD BUTTON)
        if has_main_channel_link and not is_verified and not is_loop_detected:
            # Send ONLY text message (no file attachment, no password button)
            # This is the monetization/copyright protection case
            # Password button should only appear when user clicks shortened link
            
            # Feature: Add Preview Link Button if set
            kb = []
            preview_link = post.get("preview_link")
            if preview_link:
                kb.append([InlineKeyboardButton("👁 Post Preview", url=preview_link)])
            
            # We already have the text in final_caption
            # Ensure we don't block other buttons if we ever add them, but currently none.
            
            reply_markup = InlineKeyboardMarkup(kb) if kb else None
            
            sent_msg = await update.message.reply_text(
                final_caption, 
                parse_mode=ParseMode.HTML, 
                protect_content=is_protected,
                reply_markup=reply_markup
            )
            
        # CASE 2: No Main Channel Short Link → Send actual file/content
        elif post_type == "file":
             # Password button for file posts
             reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Password", callback_data=f"pass_{post_id}")]])
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
                 
        else: # Link type (no main channel short link)
            # Password button for link posts
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔑 Password", callback_data=f"pass_{post_id}")]])
            sent_msg = await update.message.reply_text(final_caption, parse_mode=ParseMode.HTML, protect_content=is_protected, reply_markup=reply_markup)
            
        # 6. Schedule Auto-Delete
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
    if not post:
        await query.answer("❌ Post not found.", show_alert=True)
        return
    
    # Get password (may be empty/None)
    password = post.get("password", "")
    
    # If no password is set, show default message
    if not password:
        await query.answer("ℹ️ No password required", show_alert=False)
        sent = await query.message.reply_text(
            "🔑 <b>Password:</b>\n<code>No password required for this post</code>", 
            parse_mode=ParseMode.HTML
        )
        # Auto-delete after 30 seconds
        context.job_queue.run_once(
            lambda ctx: ctx.bot.delete_message(chat_id=query.message.chat_id, message_id=sent.message_id),
            30
        )
        return
        
    # Show helpful instruction in popup
    await query.answer("👆 Tap the password to copy it!", show_alert=False)
    
    # Send password in code block (tap to copy)
    sent = await query.message.reply_text(
        f"🔑 <b>Password</b> (tap to copy):\n<code>{password}</code>", 
        parse_mode=ParseMode.HTML
    )
    
    # Auto-delete password message after 60 seconds for security
    context.job_queue.run_once(
        lambda ctx: ctx.bot.delete_message(chat_id=query.message.chat_id, message_id=sent.message_id),
        60
    )

