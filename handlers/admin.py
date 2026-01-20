from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
import html
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from config import ADMIN_ID, MAIN_CHANNEL_ID
from storage import add_post, save_template, get_templates, get_message_template, get_help_link, get_post, get_main_template, update_post, get_latest_post_id, get_last_news, save_last_news, get_auto_delete_timer
from utils.helpers import send_temp_message, show_loading, escape_markdown_v2, check_admin, validate_link
import time
import logging
import datetime

# States
SELECT_TYPE, UPLOAD_FILE, INPUT_LINK, EDIT_CAPTION, INPUT_PASSWORD, SELECT_CATEGORY, CONFIRM, INPUT_TIMER = range(8)
# Main Channel Flow States
MC_INPUT_ID, MC_INPUT_LINK, MC_INPUT_NEWS, MC_CONFIRM, MC_SCHEDULE, MC_SCHED_DATE, MC_SCHED_TIME, MC_SCHEDULE_CONFIRM = range(6, 14)

# Keyboards
DASHBOARD_KB = [
    ["➕ Create Post", "📦 Bulk Create"],
    ["📢 Main Channel Post", "⏳ Scheduled Posts"],
    ["📝 Post Manager", "📂 Categories"],
    ["👥 Users", "📢 Broadcast"],
    ["⚙️ Settings", "📊 Statistics"],
    ["🔍 Search", "💾 Backup & Export"],
    ["🧹 Clear Chat"]
]

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    text = (
        "🏠 *Admin Dashboard*\n\n"
        "Select an action below:"
    )
    markup = ReplyKeyboardMarkup(DASHBOARD_KB, resize_keyboard=True)
    
    if update.callback_query:
        # If triggered by a button (e.g., from Post Manager), we need to send a fresh message
        await update.callback_query.answer()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels and ends the conversation."""
    await update.message.reply_text(
        "❌ Action cancelled.", reply_markup=ReplyKeyboardMarkup(DASHBOARD_KB, resize_keyboard=True)
    )
    return ConversationHandler.END

async def global_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle global menu buttons inside a conversation."""
    text = update.message.text
    
    if text == "🏠 Dashboard":
        return await admin_dashboard(update, context)
        
    elif text == "📝 Post Manager":
        from handlers.manager import post_manager
        await post_manager(update, context)
        return ConversationHandler.END

    elif text == "📢 Main Channel Post":
        # End current conversation so the next click works
        await update.message.reply_text("🔄 Switching modes... Please click **Main Channel Post** again.", parse_mode="Markdown")
        return ConversationHandler.END

    elif text == "⏳ Scheduled Posts":
         await scheduled_dashboard(update, context)
         return ConversationHandler.END

    elif text == "➕ Create Post":
         await update.message.reply_text("🔄 Switching modes... Please click **Create Post** again.", parse_mode="Markdown")
         return ConversationHandler.END
         
    elif text == "⏳ Scheduled Posts":
         # We need to import the handler. But checking other imports, we typically import inside function to avoid circular deps if needed.
         # But scheduled_dashboard is in this file (admin.py) at the bottom? No, I defined it in admin.py previously.
         await scheduled_dashboard(update, context)
         return ConversationHandler.END

    elif text == "📦 Bulk Create":
         await update.message.reply_text("🔄 Switching modes... Please click **Bulk Create** again.", parse_mode="Markdown")
         return ConversationHandler.END
         
    elif text == "🔍 Search":
         await update.message.reply_text("🔄 Switching modes... Please click **Search** again.", parse_mode="Markdown")
         return ConversationHandler.END
        
    elif text == "📂 Categories":
        from handlers.categories import category_dashboard
        await category_dashboard(update, context)
        return ConversationHandler.END
        
    elif text == "⚙️ Settings":
        from handlers.settings import settings_dashboard
        await settings_dashboard(update, context)
        return ConversationHandler.END
        
    elif text == "📊 Statistics":
        from handlers.stats import stats_dashboard
        await stats_dashboard(update, context)
        return ConversationHandler.END
        
    elif text == "💾 Backup & Export":
        from handlers.backup import export_data
        await export_data(update, context)
        return ConversationHandler.END

    elif text == "👥 Users":
        from handlers.users_admin import users_dashboard
        await users_dashboard(update, context)
        return ConversationHandler.END
        
    elif text == "📢 Broadcast":
        from handlers.broadcast import broadcast_dashboard
        await broadcast_dashboard(update, context)
        return ConversationHandler.END

    elif text == "🧹 Clear Chat":
        await clear_chat_history(update, context)
        return ConversationHandler.END
        
    elif text == "❌ Cancel":
        return await cancel(update, context)
        
    return await cancel(update, context) # Default

# Regex for all menu buttons
# Regex for all menu buttons
MENU_REGEX = "^(🏠 Dashboard|📝 Post Manager|📂 Categories|⚙️ Settings|📊 Statistics|💾 Backup & Export|🧹 Clear Chat|❌ Cancel|➕ Create Post|📦 Bulk Create|📢 Main Channel Post|🔍 Search|⏳ Scheduled Posts|👥 Users|📢 Broadcast)$"

async def scheduled_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import get_pending_scheduled_posts
    import datetime
    
    pending = get_pending_scheduled_posts()
    
    text = "⏳ **Scheduled Posts**\n\nSelect a post to manage:"
    kb = []
    
    count = 0
    now = datetime.datetime.now().timestamp()
    
    for pid, data in pending:
        if not data.get("is_scheduled"): continue
        ts = data.get("scheduled_for")
        if not ts: continue
        
        # IST
        dt = datetime.datetime.fromtimestamp(ts)
        ist = dt + datetime.timedelta(hours=5, minutes=30)
        time_str = ist.strftime('%d-%b %I:%M %p')
        
        label = f"#{pid} - {time_str}"
        kb.append([InlineKeyboardButton(label, callback_data=f"sched_manage_{pid}")])
        count += 1
        
    if count == 0:
        text = "⏳ **Scheduled Posts**\n\nNo active scheduled posts."
    
    # Add Refresh/Dashboard
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="sched_refresh"), InlineKeyboardButton("🏠 Dashboard", callback_data="sched_dashboard")])
    
    current_reply_markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=current_reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=current_reply_markup, parse_mode=ParseMode.MARKDOWN)

# --- SCHEDULE SCHEDULE ACTIONS ---
SCHED_DATE, SCHED_TIME = range(100, 102)

async def handle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "sched_refresh" or data == "sched_list":
        await scheduled_dashboard(update, context)
        return
        
    if data == "sched_dashboard":
        await query.message.delete()
        await admin_dashboard(update, context)
        return

    if data.startswith("sched_manage_"):
        pid = data.split("_")[-1]
        post = get_post(pid)
        if not post:
             await query.answer("Post not found", show_alert=True)
             await scheduled_dashboard(update, context)
             return
             
        ts = post.get("scheduled_for")
        dt = datetime.datetime.fromtimestamp(ts)
        ist = dt + datetime.timedelta(hours=5, minutes=30)
        time_str = ist.strftime('%d-%b %I:%M %p')
        
        text = (
            f"⏳ **Managing Post #{pid}**\n\n"
            f"Scheduled for: `{time_str}` IST\n"
            f"Channel: {post.get('target_chat_id')}\n"
            f"Preview: {post.get('channel_preview_text')[:50]}..."
        )
        
        kb = [
            [InlineKeyboardButton("🚀 Post Now", callback_data=f"sched_now_{pid}")],
            [InlineKeyboardButton("👁 Preview Message", callback_data=f"sched_preview_{pid}")],
            [InlineKeyboardButton("✏ Edit Time", callback_data=f"sched_edit_{pid}")],
            [InlineKeyboardButton("🗑 Delete Schedule", callback_data=f"sched_del_{pid}")],
            [InlineKeyboardButton("🔙 Back", callback_data="sched_list")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("sched_preview_"):
        pid = data.split("_")[-1]
        post = get_post(pid)
        if not post:
             await query.answer("Post not found", show_alert=True)
             return
             
        preview_text = post.get("channel_preview_text", "No Content")
        try:
             # Send as new message so we don't destroy the menu
             await query.message.reply_text(f"⬇️ **Preview for #{pid}**:\n\n{preview_text}", parse_mode=ParseMode.HTML)
             await query.answer()
        except Exception as e:
             await query.answer(f"Preview Failed: {e}", show_alert=True)
        
    elif data.startswith("sched_del_"):
        pid = data.split("_")[-1]
        
        # Remove job
        jobs = context.job_queue.get_jobs_by_name(f"sched_{pid}")
        for j in jobs: j.schedule_removal()
        
        # Update DB
        update_post(pid, {"is_scheduled": False, "status": "active", "scheduled_for": None})
        
        await query.answer("✅ Schedule deleted!")
        await scheduled_dashboard(update, context)
        
    elif data.startswith("sched_now_"):
        pid = data.split("_")[-1]
        
        # Remove job
        jobs = context.job_queue.get_jobs_by_name(f"sched_{pid}")
        for j in jobs: j.schedule_removal()
        
        # Execute immediately
        post = get_post(pid)
        target_chat_id = post.get("target_chat_id")
        preview_text = post.get("channel_preview_text")

        # Call helper directly
        success = await execute_scheduled_post(context, pid, target_chat_id, preview_text)
        
        if success:
            await query.answer("✅ Posted to channel!")
            await scheduled_dashboard(update, context)
        else:
             await query.answer("❌ Failed to post. Check logs.", show_alert=True)


# --- EDIT SCHEDULE CONVERSATION ---

async def start_edit_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pid = query.data.split("_")[-1]
    context.user_data['sched_edit_pid'] = pid
    
    await query.answer()
    await query.answer()
    await query.message.reply_text(
        f"⏳ **Update Time for #{pid}**\n\n"
        "Please select the **Date** for the schedule:",
        reply_markup=ReplyKeyboardMarkup([["📅 Today", "🗓 Custom Date"], ["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return SCHED_DATE

async def edit_sched_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("❌ Edit Cancelled.")
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    import datetime
    now_utc = datetime.datetime.utcnow()
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset
    
    selected_date = None
    
    if text == "📅 Today":
        selected_date = now_ist.date()
        await update.message.reply_text(
            f"📅 Selected: **Today** ({selected_date.strftime('%d-%m-%Y')})\n\n"
            "⏰ Enter Time in **HH:MM** format (24 hours):",
             reply_markup=ReplyKeyboardMarkup([["⬅️ Change Date", "❌ Cancel"]], resize_keyboard=True),
             parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['edit_sched_date'] = selected_date.isoformat()
        return SCHED_TIME
        
    elif text == "🗓 Custom Date":
        await update.message.reply_text(
            "🗓 Enter Date in **DD/MM/YYYY** format:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return SCHED_DATE
        
    else:
        # Validate DD/MM/YYYY
        import re
        date_pattern = r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])/(19|20)\d{2}$"
        
        if not re.match(date_pattern, text):
             await update.message.reply_text(
                 "❌ Invalid input.\n"
                 "Expected format: DD/MM/YYYY\n"
                 "Example: 20/01/2026"
             )
             return SCHED_DATE
             
        try:
             d = datetime.datetime.strptime(text, "%d/%m/%Y").date()
             if d < now_ist.date():
                 await update.message.reply_text("⚠ Date cannot be in the past. Try again.")
                 return SCHED_DATE
                 
             selected_date = d
             context.user_data['edit_sched_date'] = selected_date.isoformat()
             
             await update.message.reply_text(
                f"📅 Selected: **{selected_date.strftime('%d-%m-%Y')}**\n\n"
                "⏰ Enter Time in **HH:MM** format (24 hours):",
                 reply_markup=ReplyKeyboardMarkup([["⬅️ Change Date", "❌ Cancel"]], resize_keyboard=True),
                 parse_mode=ParseMode.MARKDOWN
            )
             return SCHED_TIME
        except ValueError:
             await update.message.reply_text(
                 "❌ Invalid input.\n"
                 "Expected format: DD/MM/YYYY\n"
                 "Example: 20/01/2026"
             )
             return SCHED_DATE

async def edit_sched_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("❌ Edit Cancelled.")
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    pid = context.user_data.get('sched_edit_pid')
    
    if text == "⬅️ Change Date":
        await update.message.reply_text(
            f"⏳ **Update Time for #{pid}**\n\n"
            "Please select the **Date** for the schedule:",
            reply_markup=ReplyKeyboardMarkup([["📅 Today", "🗓 Custom Date"], ["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return SCHED_DATE

    date_str = context.user_data.get('edit_sched_date')
    if not date_str:
        await update.message.reply_text("⚠ Session Error. Please start over.")
        return await admin_dashboard(update, context)
        
    import datetime
    selected_date = datetime.date.fromisoformat(date_str)
    
    # Strict Time Validation
    import re
    time_pattern = r"^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$"
    
    if not re.match(time_pattern, text):
         await update.message.reply_text(
             "❌ Invalid time format.\n"
             "Please enter time in 24h format (HH:MM)\n"
             "Example: 09:30 or 21:45"
         )
         return SCHED_TIME
         
    try:
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        
        # Construct Target
        target_ist = datetime.datetime.combine(selected_date, datetime.time(hour, minute))
        
        # Check Future
        now_utc = datetime.datetime.utcnow()
        ist_offset = datetime.timedelta(hours=5, minutes=30)
        now_ist = now_utc + ist_offset
        
        if target_ist <= now_ist:
             await update.message.reply_text("⚠ Scheduled time must be in the future.")
             return SCHED_TIME
             
        # Calculate Delay
        target_utc = target_ist - ist_offset
        delay_seconds = (target_utc - now_utc).total_seconds()
        
        # Warn Conflict (Reuse logic)
        from storage import get_pending_scheduled_posts
        try:
            pending = get_pending_scheduled_posts()
            for p_id, data in pending:
                if str(p_id) == str(pid): continue 
                existing_ts = data.get("scheduled_for")
                if existing_ts:
                    diff = abs(target_utc.timestamp() - int(existing_ts))
                    if diff < 300:
                         await update.message.reply_text(
                             "⚠️ **Warning: Another post is scheduled within 5 minutes.**\n"
                             "Updating anyway..."
                         )
                         break
        except: pass

        # Re-Schedule Logic
        jobs = context.job_queue.get_jobs_by_name(f"sched_{pid}")
        for j in jobs: j.schedule_removal()
        
        post = get_post(pid)
        target_chat_id = post.get("target_chat_id")
        preview_text = post.get("channel_preview_text")
        
        # Update DB
        scheduled_for_ts = target_utc.timestamp()
        update_post(pid, {
            "scheduled_for": int(scheduled_for_ts)
        })
        
        # New Job
        context.job_queue.run_once(
            send_scheduled_post_job, 
            delay_seconds,
            chat_id=target_chat_id,
            name=f"sched_{pid}",
            data={
                "chat_id": target_chat_id,
                "text": preview_text,
                "post_id": pid
            }
        )
        
        new_ist_str = target_ist.strftime('%d-%b %I:%M %p')
        await update.message.reply_text(f"✅ **Updated!** New time: `{new_ist_str} IST`", parse_mode=ParseMode.MARKDOWN)
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    except ValueError:
         await update.message.reply_text("❌ Error processing time.")
         return SCHED_TIME
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return SCHED_TIME

sched_edit_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_schedule_time, pattern="^sched_edit_")],
    states={
        SCHED_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_sched_date_input)],
        SCHED_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_sched_time_input)]
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

# --- CREATE POST WORKFLOW ---

async def start_create_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    # Clear previous context
    context.user_data.clear()
    
    markup = ReplyKeyboardMarkup([["🖇 File Post", "🔗 Link Post"], ["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "🆕 *Create New Post*\n\n"
        "Select the type of post you want to create:",
        reply_markup=markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECT_TYPE

async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "❌ Cancel":
        return await cancel(update, context)
        
    if choice == "🖇 File Post":
        context.user_data['type'] = 'file'
        await update.message.reply_text(
            "📂 *Upload Your File*\n\n"
            "Please send the file (Video, Document, Photo, Audio) you want to share.\n"
            "You can add a caption now, or I will ask you to edit it later.",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN
        )
        return UPLOAD_FILE
        
    elif choice == "🔗 Link Post":
        context.user_data['type'] = 'link'
        await update.message.reply_text(
            "🔗 *Paste Your Link*\n\n"
            "Please paste the URL you want to share:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode=ParseMode.MARKDOWN
        )
        return INPUT_LINK
    
    else:
        await update.message.reply_text(
            "⚠ Invalid option. Please select '🖇 File Post' or '🔗 Link Post' using the buttons below.",
            reply_markup=ReplyKeyboardMarkup([["🖇 File Post", "🔗 Link Post"], ["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return SELECT_TYPE

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    
    # Detect file type
    if msg.document:
        f = msg.document
        context.user_data['file_type'] = 'document'
        context.user_data['file_name'] = f.file_name
        context.user_data['file_id'] = f.file_id
    elif msg.video:
        f = msg.video
        context.user_data['file_type'] = 'video'
        context.user_data['file_name'] = f.file_name or "video.mp4"
        context.user_data['file_id'] = f.file_id
    elif msg.photo:
        f = msg.photo[-1] # Best quality
        context.user_data['file_type'] = 'photo'
        context.user_data['file_name'] = "photo.jpg"
        context.user_data['file_id'] = f.file_id
    elif msg.audio:
        f = msg.audio
        context.user_data['file_type'] = 'audio'
        context.user_data['file_name'] = f.file_name or "audio.mp3"
        context.user_data['file_id'] = f.file_id
    else:
        await update.message.reply_text("⚠ Unsupported file type. Please upload a Document, Video, Photo, or Audio.")
        return UPLOAD_FILE
        
    # If Link post, we want caption. But user said "file or zip only" for password workflow.
    # Existing link logic calls handle_link_input -> ask_edit_caption.
    # So we only change FILE workflow.
    
    # New Logic: Ask for Password instead of Caption
    await update.message.reply_text(
        "🔐 **File Received!**\n\n"
        "Please enter the **Password** for this file (e.g. `1089`).", 
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return INPUT_PASSWORD
    
async def handle_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    
    if password == "❌ Cancel":
        return await cancel(update, context)
        
    # Calculate Next Post ID to show in caption
    # Calculate Next Post ID to show in caption
    next_id = get_latest_post_id() + 1
    
    # Auto-generate caption
    caption = f"Post: {next_id}\nPassword: {password}"
    context.user_data['caption'] = caption
    
    await update.message.reply_text(f"✅ Password saved! Auto-Caption generated:\n`{caption}`", parse_mode=ParseMode.MARKDOWN)
    
    # Skip EDIT_CAPTION, go straight to Category
    # Initialize empty selection for Multi-Select
    context.user_data['selected_categories'] = []
    return await show_category_selection_ui(update, context)
    return SELECT_CATEGORY

async def handle_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    
    # Auto-prepend https:// if missing
    link = validate_link(link)
    
    if not link:
        await update.message.reply_text("❌ Invalid link format. Please try again (e.g. google.com).")
        return INPUT_LINK
        
    context.user_data['link'] = link
    context.user_data['caption'] = "Check this link! 👇\n{link}" # Default template for links
    
    return await ask_edit_caption(update, context)

async def ask_edit_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_caption = context.user_data.get('caption', '')
    
    text = (
        "📝 *Edit Caption / Template*\n\n"
        f"current caption:\n```\n{current_caption}\n```\n\n"
        "Send new text to replace, or click '✅ Keep Current' to proceed."
    )
    
    kb = [["✅ Keep Current"], ["❌ Cancel", "🏠 Dashboard"]]
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return EDIT_CAPTION

async def edit_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "❌ Cancel":
        return await cancel(update, context)
        
    # Check for Keep Current (fuzzy match or exact)
    if text == "✅ Keep Current":
        pass # Keep existing caption
    else:
        # Update caption
        context.user_data['caption'] = text
        await send_temp_message(context, update.effective_chat.id, "✅ Caption updated!", delay=3)
    
    # Proceed to Category with Multi-Select logic
    context.user_data['selected_categories'] = []
    return await show_category_selection_ui(update, context)
    return SELECT_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Multi-Category Selection Logic
    
    # Initialize regex for Done/Clear
    if update.message.text == "✅ Done":
        selected = context.user_data.get('selected_categories', [])
        if not selected:
            await update.message.reply_text("⚠ Please select at least one category.")
            return SELECT_CATEGORY
            
        # Join with double space as requested: "Comedy  Action"
        final_cat_str = "  ".join(selected)
        context.user_data['category'] = final_cat_str
        try:
            return await show_final_confirmation(update, context)
        except Exception as e:
             await update.message.reply_text(f"❌ Error proceeding: {e}")
             return SELECT_CATEGORY

    if update.message.text == "❌ Clear":
        context.user_data['selected_categories'] = []
        await update.message.reply_text("🗑 Selection cleared.", parse_mode=ParseMode.MARKDOWN)
        # Re-show list
        return await show_category_selection_ui(update, context)

    cat = update.message.text.replace("✅ ", "") # Remove checkmark if clicked again (optional UX)
    # Actually, we rely on the text sent by keyboard.
    # But clean it just in case.
    
    # Validate category
    from storage import get_categories
    valid_cats = list(get_categories().values())
    valid_names = [c['name'] for c in valid_cats]
    
    if cat == "❌ Skip":
        context.user_data['category'] = "Uncategorized"
        return await show_final_confirmation(update, context)
        
    # Toggle logic
    selected = context.user_data.get('selected_categories', [])
    
    # Check if valid
    if cat not in valid_names:
        # Check if it was a "Selected: Cat" button?
        # If we show status in buttons, the text changes.
        # Let's strip "✅ " prefix if we add it to buttons.
        clean_cat = cat.replace("✅ ", "")
        if clean_cat in valid_names:
            cat = clean_cat
        else:
            await update.message.reply_text("⚠ Please select a valid category.")
            return SELECT_CATEGORY

    if cat in selected:
        selected.remove(cat)
    else:
        selected.append(cat)
        
    context.user_data['selected_categories'] = selected
    
    # Re-render UI with updated selection
    return await show_category_selection_ui(update, context)

async def show_category_selection_ui(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = context.user_data.get('selected_categories', [])
    
    from storage import get_categories
    categories_data = get_categories()
    categories = [c['name'] for c in categories_data.values()]
    if not categories:
        categories = ["Uncategorized"]
    
    # Build Keyboard with visual indicators
    kb = []
    row = []
    for cat in categories:
        label = f"✅ {cat}" if cat in selected else cat
        row.append(label)
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    # Control buttons
    kb.append(["✅ Done", "❌ Clear"])
    kb.append(["❌ Skip", "🏠 Dashboard"]) 
    
    current_sel_str = ", ".join(selected) if selected else "(None)"
    
    await update.message.reply_text(
        f"🏷 *Select Categories*\n\n"
        f"Selected: *{current_sel_str}*\n\n"
        "Click to toggle. Press **Done** when finished.",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECT_CATEGORY

async def show_final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = context.user_data
        
        # Timer Display
        timer_val = data.get('auto_delete_timer')
        global_timer = get_auto_delete_timer()
        timer_str = f"{timer_val} mins" if timer_val else f"Default ({int(global_timer/60)} mins)"
        
        # Escape content for HTML safety
        ptype = html.escape(str(data.get('type', 'N/A')))
        category = html.escape(str(data.get('category', 'N/A')))
        file_name = html.escape(str(data.get('file_name', 'N/A')))
        link = html.escape(str(data.get('link', 'N/A')))
        caption = html.escape(str(data.get('caption', '')))
        
        preview_text = (
            "📋 <b>Confirm Post Creation</b>\n\n"
            f"<b>Type</b>: {ptype}\n"
            f"<b>Category</b>: {category}\n"
            f"<b>File</b>: {file_name}\n"
            f"<b>Link</b>: {link}\n"
            f"<b>Timer</b>: {timer_str}\n\n"
            "<b>Caption/Content</b>:\n"
            f"<i>{caption}</i>"
        )
        
        kb = [["✅ Create Post", "Draft Mode"], ["⏱️ Set Timer", "✏️ Edit Again"], ["❌ Cancel"]]
        await update.message.reply_text(
            preview_text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
            parse_mode=ParseMode.HTML
        )
        return CONFIRM
    except Exception as e:
        print(f"Error in show_final_confirmation: {e}")
        await update.message.reply_text(
            f"⚠ Error rendering confirmation: {e}\n\nPlease try again or click Cancel.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
        )
        return CONFIRM

async def final_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "❌ Cancel":
        return await cancel(update, context)
        
    if choice == "✏️ Edit Again":
        return await ask_edit_caption(update, context)

    if choice == "⏱️ Set Timer":
        await update.message.reply_text(
            "⏱️ *Set Custom Auto-Delete Timer*\n\n"
            "Enter the time in **minutes** (e.g. `10`, `60`).\n"
            "Enter `0` to reset to Default.",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return INPUT_TIMER
    
    status = "active"
    if choice == "Draft Mode":
        status = "draft"
    
    # Save to storage
    data = context.user_data
    post_id = add_post({
        "type": data['type'],
        "file_id": data.get('file_id'),
        "file_type": data.get('file_type'),
        "file_name": data.get('file_name'),
        "link": data.get('link'),
        "caption": data['caption'],
        "category": data['category'],
        "status": status,
        "auto_delete_timer": data.get('auto_delete_timer'), # Feature
        # Default empty fields
        "tags": [],
        "views": 0,
        "note": ""
    })
    
    bot_username = context.bot.username
    from utils.helpers import encode_payload
    encoded_id = encode_payload(post_id)
    deep_link = f"https://t.me/{bot_username}?start={encoded_id}"
    
    # Render Preview
    template = get_message_template()
    post_link = data.get('link') or ""
    
    import re
    if not post_link:
        # Magic: If link is empty, remove related header line
        template = re.sub(r"(?i)^.*(Download/Watch Link|Link👇).*$\n?", "", template, flags=re.MULTILINE)
    
    custom_timer_mins = data.get('auto_delete_timer')
    preview_seconds = int(custom_timer_mins) * 60 if custom_timer_mins else get_auto_delete_timer()

    variables = {
        "post_id": post_id,
        "category": data['category'],
        "time": int(preview_seconds/60),
        "time_sec": preview_seconds,
        "link": post_link,
        "how_to_open_link": get_help_link()
    }
    
    # Pre-format caption
    raw_caption = data.get('caption', '')
    try:
        processed_caption = raw_caption.format(**variables)
    except:
        processed_caption = raw_caption
    
    variables["caption"] = processed_caption
    
    try:
        preview_text = template.format(**variables)
    except Exception as e:
        preview_text = f"⚠ Preview Error: {e}"

    success_msg = (
        f"✅ *Post Created Successfully!* (#{post_id})\n\n"
        f"🔗 *Copy Link*:\n`{deep_link}`\n\n"
        f"⬇️ *User Preview* ⬇️\n"
        f"------------------\n"
        f"{preview_text}\n"
        f"------------------"
    )
    
    # Note: If preview is too long or has HTML tags, reply_text with markdown might fail if users put raw HTML tags in template. 
    # But we are using ParseMode.MARKDOWN for success_msg. 
    # If preview_text contains characters that break markdown (like unclosed * or _), it might error.
    # Ideally we should send preview as separate message or just be careful. 
    # For now, let's try to keep it simple. If template is HTML based but we send as Markdown, it might look wrong.
    # Actually, user.py uses HTML parse mode. admin.py uses MARKDOWN. Mixing them is tricky in one message.
    # Let's send the success message as HTML to match user.py's rendering style for the preview part? 
    # Or just send preview as a second message with HTML parse mode.
    
    await update.message.reply_text(success_msg.replace("⬇️ *User Preview* ⬇️", "⬇️ User Preview (Raw) ⬇️"), parse_mode=None) 
    # Sending without parse_mode to avoid errors with complex templates for now, 
    # OR better: Send success msg (Markdown) first, then Preview (HTML) separately.
    
    # Re-doing the block to send separately for safety
    await update.message.reply_text(
        f"✅ *Post Created Successfully!* (#{post_id})\n\n"
        f"🔗 *Copy Link*:\n`{deep_link}`",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await update.message.reply_text(
        f"⬇️ *User View Preview*:\n\n{preview_text}",
        parse_mode=ParseMode.HTML
    )
    
    # Return to dashboard
    # Return to dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

async def clear_chat_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Attempt to delete the last 50 messages."""
    if not check_admin(update.effective_user.id): return
    
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Send temporary status
    status_msg = await update.message.reply_text("🧹 Clearing chat...")
    
    # Loop backwards to delete previous messages
    # We try to delete the trigger message (message_id) and 50 before it
    items_to_delete = [message_id] + list(range(message_id - 1, message_id - 51, -1))
    
    count = 0
    for mid in items_to_delete:
        try:
            await context.bot.delete_message(chat_id, mid)
            count += 1
        except Exception:
            pass # Ignore errors (user messages, old messages, etc)
            
    # Delete the status message itself
    try:
        await context.bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass
    
    await admin_dashboard(update, context)

# Helper for Timer
async def set_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_final_confirmation(update, context)
        
    if not text.isdigit():
        await update.message.reply_text("⚠ Please enter a valid number of minutes.")
        return INPUT_TIMER
        
    mins = int(text)
    if mins == 0:
        if 'auto_delete_timer' in context.user_data:
            del context.user_data['auto_delete_timer']
        await update.message.reply_text("✅ Timer reset to Global Default.")
    else:
        context.user_data['auto_delete_timer'] = mins
        await update.message.reply_text(f"✅ Timer set to **{mins} mins**.")
        
    return await show_final_confirmation(update, context)

# Export handler
create_post_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^➕ Create Post$"), start_create_post)],
    states={
        SELECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), select_type)],
        UPLOAD_FILE: [MessageHandler(filters.ATTACHMENT | filters.VIDEO | filters.PHOTO | filters.AUDIO | filters.Document.ALL, handle_file_upload)],
        INPUT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), handle_link_input)],
        INPUT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), handle_password_input)],
        EDIT_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), edit_caption)],
        SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), select_category)],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), final_confirm)],
        INPUT_TIMER: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), set_timer)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ],
    allow_reentry=True
)

# --- MAIN CHANNEL POST FLOW ---

async def start_main_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    context.user_data.clear()
    
    # Suggest latest ID
    # Suggest latest ID
    suggested = get_latest_post_id()
    
    await update.message.reply_text(
        "📢 *Main Channel Post*\n\n"
        f"Please enter the **Post ID** you want to share.\n"
        f"_(Latest Post ID: {suggested})_",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return MC_INPUT_ID

async def mc_input_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    post_id = text.strip()
    post = get_post(post_id)
    
    if not post:
        await update.message.reply_text("❌ Post not found. Please try again.")
        return MC_INPUT_ID
        
    context.user_data['mc_post_id'] = post_id
    
    # Generate Deep Link
    # Generate Deep Link
    bot_username = context.bot.username
    from utils.helpers import encode_payload
    encoded_id = encode_payload(post_id)
    deep_link = f"https://t.me/{bot_username}?start={encoded_id}"
    context.user_data['mc_deep_link'] = deep_link
    
    await update.message.reply_text(
        f"✅ Validated Post #{post_id}\n\n"
        f"🔗 **Deep Link**:\n`{deep_link}`\n\n"
        "Please send the **Shortened Link** (or any link) you want to use.\n"
        "Click 'Skip' to use the raw deep link.",
        reply_markup=ReplyKeyboardMarkup([["⏭️ Skip"], ["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return MC_INPUT_LINK

async def mc_input_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    if text.lower() == 'skip' or text == "⏭️ Skip":
        short_link = context.user_data['mc_deep_link']
    else:

        text_in = text.strip()
        short_link = validate_link(text_in)
        
        if not short_link:
             await update.message.reply_text("❌ Invalid link format. Please try again.")
             return MC_INPUT_LINK
            
    context.user_data['mc_short_link'] = short_link
    
    await update.message.reply_text(
        "📰 **Enter News/Content**\n\n"
        "Please send the text content (News, ignoring text, etc.) to place at the top.",
        reply_markup=ReplyKeyboardMarkup([["🔄 Use Last News"], ["❌ Cancel"]], resize_keyboard=True, one_time_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return MC_INPUT_NEWS

async def mc_input_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Debug
        # await update.message.reply_text("Debug: Processing news...") # Temporary
        
        text = update.message.text
        if text == "❌ Cancel": return await cancel(update, context)
        
        # Check if "Use Last News"
        if text == "🔄 Use Last News":
            last = get_last_news()
            if last:
                text = last
                await update.message.reply_text(f"🔄 Using last news:\n{text}")
            else:
                 await update.message.reply_text("⚠ No previous news found. Please enter text.")
                 return MC_INPUT_NEWS
        
        # Save this as new last news (Raw)
        try:
            save_last_news(text)
        except Exception as e:
            print(f"Error saving last news: {e}")
        
        # Auto-apply strikethrough as requested
        escaped_text = html.escape(text)
        context.user_data['mc_news'] = f"<s>{escaped_text}</s>"
        return await mc_render_preview(update, context)
    except Exception as e:
        print(f"Error in mc_input_news: {e}")
        await update.message.reply_text(f"❌ Error processing input: {e}")
        return MC_INPUT_NEWS

async def mc_render_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Prepare variables
        data = context.user_data
        
        try:
             hl = get_help_link()
        except Exception as e:
             await update.message.reply_text(f"❌ Error getting help link: {e}")
             return MC_INPUT_NEWS

        variables = {
            "post_id": data.get('mc_post_id', 'N/A'),
            "short_link": data.get('mc_short_link', 'N/A'),
            "news": data.get('mc_news', 'N/A'),
            "how_to_open_link": hl
        }
        
        try:
            template = get_main_template()
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting template: {e}")
            return MC_INPUT_NEWS
        
        # Validation
        missing = []
        import string
        # Get field names from template
        try:
            required_keys = [t[1] for t in string.Formatter().parse(template) if t[1] is not None]
        except Exception as e:
             await update.message.reply_text(f"❌ Error parsing template: {e}")
             return MC_INPUT_NEWS
        
        for key in required_keys:
            if key not in variables:
                missing.append(key)
                
        if missing:
            await update.message.reply_text(
                f"❌ Template Error: The following placeholders are missing data: {', '.join(missing)}\n"
                "Please check your template or inputs."
            )
            return MC_INPUT_NEWS
            
        try:
            preview_text = template.format(**variables)
            context.user_data['mc_preview_text'] = preview_text
        except Exception as e:
            await update.message.reply_text(f"❌ Formatting Error: {e}")
            return MC_INPUT_NEWS
    
        # Show Buttons
        kb = [
            ["🚀 Post to Channel", "⏰ Schedule"],
            ["👁️ Preview as Channel", "📋 Copy Content"],
            ["❌ Cancel"]
        ]
        
        try:
            await update.message.reply_text(
                f"📄 **Preview**:\n\n{preview_text}\n\nSelect an action:",
                reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Preview Error (HTML): {e}\n\nRaw Text:\n{preview_text}")
            return MC_INPUT_NEWS
        return MC_CONFIRM

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # print(f"Error in mc_render_preview: {e}\n{tb}")
        # Send TB to user (Debug only)
        # Truncate if too long
        if len(tb) > 4000: tb = tb[:4000]
        await update.message.reply_text(f"❌ unexpected error in preview: {e}\n\nTraceback:\n`{tb}`", parse_mode=ParseMode.MARKDOWN)
        return MC_INPUT_NEWS

async def mc_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    data = context.user_data
    preview_text = data.get('mc_preview_text', "")
    post_id = data.get('mc_post_id')
    
    if text == "📋 Copy Content":
        await update.message.reply_text(f"`{preview_text}`", parse_mode=ParseMode.MARKDOWN)
        return MC_CONFIRM
        
    elif text == "👁️ Preview as Channel":
        # Dry Run
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=preview_text,
                parse_mode=ParseMode.HTML
            )
            await update.message.reply_text("✅ Preview sent above.")
        except Exception as e:
            await update.message.reply_text(f"❌ Preview failed: {e}")
        return MC_CONFIRM
        
    elif text == "🚀 Post to Channel":
        if not MAIN_CHANNEL_ID:
            await update.message.reply_text("❌ MAIN_CHANNEL_ID is not configured in .env")
            return MC_CONFIRM
            
        try:
            msg = await context.bot.send_message(
                chat_id=MAIN_CHANNEL_ID,
                text=preview_text,
                parse_mode=ParseMode.HTML
            )
            
            # Update DB
            update_post(post_id, {
                "posted_to_channel": True,
                "posted_at": int(time.time()),
                "channel_message_id": msg.message_id
            })
            await update.message.reply_text(f"✅ Posted Successfully! (Msg ID: {msg.message_id})")
            await admin_dashboard(update, context)
            return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to post: {e}")
            return MC_CONFIRM
            
    elif text == "⏰ Schedule":
        # Check duplicate
        current_jobs = context.job_queue.get_jobs_by_name(f"sched_{post_id}")
        if current_jobs:
            await update.message.reply_text(
                f"⚠ **Warning**: Post #{post_id} is already scheduled.\n"
                "Do you want to schedule another one?",
                reply_markup=ReplyKeyboardMarkup([["✅ Yes, Schedule", "❌ Cancel"]], resize_keyboard=True),
                parse_mode=ParseMode.MARKDOWN
            )
            return MC_SCHEDULE
            
        await update.message.reply_text(
            "⏳ **Schedule Post**\n\n"
            "Please select the **Date** for the schedule:",
            reply_markup=ReplyKeyboardMarkup([["📅 Today", "🗓 Custom Date"], ["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MC_SCHED_DATE

    return MC_CONFIRM

async def execute_scheduled_post(context: ContextTypes.DEFAULT_TYPE, post_id: str, chat_id: int, text: str):
    """Core logic to send post and update DB. Returns True if successful."""
    try:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
        
        # Update DB
        update_post(post_id, {
            "posted_to_channel": True,
            "posted_at": int(time.time()),
            "channel_message_id": msg.message_id,
            "is_scheduled": False, # Done
            "scheduled_for": None,
            "status": "active",
            "retry_count": 0
        })
        print(f"Scheduled Post #{post_id} sent successfully.")
        return True
        
    except Exception as e:
        print(f"Failed to send scheduled post #{post_id}: {e}")
        return False

async def send_scheduled_post_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to send the scheduled post. Uses execute_scheduled_post."""
    job = context.job
    data = job.data
    
    chat_id = data['chat_id']
    text = data['text']
    post_id = data['post_id']
    
    success = await execute_scheduled_post(context, post_id, chat_id, text)
    
    if not success:
        # Retry Logic
        # We need to re-read post to get current retry count? Or rely on memory?
        # Better to re-read to avoid race conditions if needed, but here simple is ok.
        post = get_post(post_id)
        if not post: return # Deleted?

        retry_count = post.get("retry_count", 0)
        
        if retry_count < 3:
            new_count = retry_count + 1
            print(f"Retrying post #{post_id} (Attempt {new_count}/3) in 60s...")
            
            update_post(post_id, {"retry_count": new_count})
            
            # Reschedule self
            context.job_queue.run_once(
                send_scheduled_post_job, 
                60, 
                chat_id=chat_id, 
                name=f"sched_{post_id}_retry",
                data=data
            )
        else:
             print(f"Max retries reached for #{post_id}. Marking as failed.")
             update_post(post_id, {
                 "status": "failed", 
                 "is_scheduled": False,
                 "note": "Failed after 3 retries (Job Queue)."
             })


async def mc_sched_date_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    import datetime
    now_utc = datetime.datetime.utcnow()
    # IST Offset
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset
    
    selected_date = None # store as date object
    
    if text == "📅 Today":
        selected_date = now_ist.date()
        await update.message.reply_text(
            f"📅 Selected: **Today** ({selected_date.strftime('%d-%m-%Y')})\n\n"
            "⏰ Enter Time in **HH:MM** format (24 hours):",
             reply_markup=ReplyKeyboardMarkup([["⬅️ Change Date", "❌ Cancel"]], resize_keyboard=True),
             parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['temp_sched_date'] = selected_date.isoformat()
        return MC_SCHED_TIME
        
    elif text == "🗓 Custom Date":
        await update.message.reply_text(
            "🗓 Enter Date in **DD/MM/YYYY** format:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MC_SCHED_DATE # Stay in this state to receive text input
        
    else:
        # Validate DD/MM/YYYY using Regex and Parsing
        import re
        date_pattern = r"^(0[1-9]|[12][0-9]|3[01])/(0[1-9]|1[0-2])/(19|20)\d{2}$"
        
        if not re.match(date_pattern, text):
             await update.message.reply_text(
                 "❌ Invalid input.\n"
                 "Expected format: DD/MM/YYYY\n"
                 "Example: 20/01/2026"
             )
             return MC_SCHED_DATE

        try:
             # Parse
             d = datetime.datetime.strptime(text, "%d/%m/%Y").date()
             
             # Check for past date
             if d < now_ist.date():
                 await update.message.reply_text("⚠ Date cannot be in the past. Try again.")
                 return MC_SCHED_DATE
                 
             selected_date = d
             await update.message.reply_text(
                f"📅 Selected: **{selected_date.strftime('%d-%m-%Y')}**\n\n"
                "⏰ Enter Time in **HH:MM** format (24 hours):",
                 reply_markup=ReplyKeyboardMarkup([["⬅️ Change Date", "❌ Cancel"]], resize_keyboard=True),
                 parse_mode=ParseMode.MARKDOWN
            )
             context.user_data['temp_sched_date'] = selected_date.isoformat()
             return MC_SCHED_TIME
             
        except ValueError:
            await update.message.reply_text(
                 "❌ Invalid input.\n"
                 "Expected format: DD/MM/YYYY\n"
                 "Example: 20/01/2026"
            )
            return MC_SCHED_DATE

async def mc_sched_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    if text == "⬅️ Change Date":
        await update.message.reply_text(
            "⏳ **Schedule Post**\n\n"
            "Please select the **Date** for the schedule:",
            reply_markup=ReplyKeyboardMarkup([["📅 Today", "🗓 Custom Date"], ["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MC_SCHED_DATE
    
    date_str = context.user_data.get('temp_sched_date')
    if not date_str:
        await update.message.reply_text("⚠ Session Error. Please start over.")
        return await admin_dashboard(update, context)
        
    import datetime
    selected_date = datetime.date.fromisoformat(date_str)
    
    try:
        # PURE STRICT VALIDATION
        # Regex for HH:MM (00-23 : 00-59)
        import re
        # This regex ensures:
        # 1. Hours: 00-19 OR 20-23
        # 2. Minutes: 00-59
        # 3. Two digits MANDATORY (Reject 9:30)
        time_pattern = r"^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$"
        
        if not re.match(time_pattern, text):
             await update.message.reply_text(
                 "❌ Invalid time format.\n"
                 "Please enter time in 24h format (HH:MM)\n"
                 "Example: 09:30 or 21:45"
             )
             return MC_SCHED_TIME

        # Safe to parse now
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        
        # Logic check (Regex covers range, but safety first)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
             await update.message.reply_text("❌ Invalid time (00-23 hours, 00-59 minutes).")
             return MC_SCHED_TIME
             
        # Construct Target IST Datetime
        target_ist = datetime.datetime.combine(selected_date, datetime.time(hour, minute))
        
        # Check against Now (IST)
        now_utc = datetime.datetime.utcnow()
        ist_offset = datetime.timedelta(hours=5, minutes=30)
        now_ist = now_utc + ist_offset
        
        if target_ist <= now_ist:
             await update.message.reply_text("⚠ Scheduled time must be in the future.")
             return MC_SCHED_TIME
             
        # Calculate Delay (for JobQueue, which uses UTC/Server time usually, or relative seconds)
        # We need relative seconds from NOW (Server Time)
        # Target(IST) -> convert to UTC -> compare with Now(UTC)
        
        target_utc = target_ist - ist_offset
        delay_seconds = (target_utc - now_utc).total_seconds()
        
        # Proceed to Confirmation
        post_id = context.user_data['mc_post_id']
        
        # Check Conflicts
        from storage import get_pending_scheduled_posts
        try:
            pending = get_pending_scheduled_posts()
            warnings = ""
            for pid, data in pending:
                if pid == post_id: continue 
                existing_time_ts = data.get("scheduled_for")
                if existing_time_ts:
                    existing_time_ts = int(existing_time_ts) # ensure int
                    # Compare UTC timestamps
                    diff = abs(target_utc.timestamp() - existing_time_ts)
                    if diff < 300: 
                        warnings = "\n⚠️ **Warning: Another post is scheduled within 5 minutes.**\nDo you want to continue?"
                        break # One warning is enough
        except Exception as e:
            warnings = ""
            
        # Store Data
        context.user_data['temp_schedule_time'] = target_utc.timestamp()
        context.user_data['temp_delay_seconds'] = delay_seconds
        
        ist_str = target_ist.strftime('%d-%b-%Y %I:%M %p')
        
        msg_text = (
            "⏳ **Confirm Schedule**\n\n"
            f"**Post**: #{post_id}\n"
            f"**Channel**: `{MAIN_CHANNEL_ID}`\n"
            f"**Time (IST)**: `{ist_str}`\n"
            f"{warnings}\n"
        )
        if not warnings:
             msg_text += "Please confirm execution."
        
        kb = [["✅ Confirm Schedule"], ["❌ Cancel"]] # Removed "Edit Time" simple button as it's multi-step now, or we can add "✏ Edit Date/Time"
        await update.message.reply_text(msg_text, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True), parse_mode=ParseMode.MARKDOWN)
        return MC_SCHEDULE_CONFIRM

    except ValueError:
        await update.message.reply_text("❌ Invalid Time Format. Use **HH:MM** (24h).")
        return MC_SCHED_TIME

            

async def mc_schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text
        if text == "❌ Cancel": return await cancel(update, context)
        
        if text == "✏ Edit Date/Time":
            await update.message.reply_text("⏳ Select Date:", reply_markup=ReplyKeyboardMarkup([["📅 Today", "🗓 Custom Date"], ["❌ Cancel"]], resize_keyboard=True))
            return MC_SCHED_DATE

        if text == "✅ Confirm Schedule":
            # Actuate
            post_id = context.user_data['mc_post_id']
            preview_text = context.user_data['mc_preview_text']
            delay_seconds = context.user_data['temp_delay_seconds']
            schedule_time_ts = context.user_data['temp_schedule_time']
            
            target_chat_id = MAIN_CHANNEL_ID
            
            # IST for final message
            schedule_time = datetime.datetime.fromtimestamp(schedule_time_ts)
            ist_time = schedule_time + datetime.timedelta(hours=5, minutes=30)
            
            try:
                 # Update DB
                update_post(post_id, {
                    "posted_to_channel": False, 
                    "is_scheduled": True,
                    "scheduled_for": int(schedule_time_ts),
                    "channel_preview_text": preview_text,
                    "target_chat_id": target_chat_id,
                    "status": "pending",
                    "retry_count": 0
                })
                
                # JobQueue
                context.job_queue.run_once(
                    send_scheduled_post_job, 
                    delay_seconds,
                    chat_id=target_chat_id,
                    name=f"sched_{post_id}",
                    data={
                        "chat_id": target_chat_id,
                        "text": preview_text,
                        "post_id": post_id
                    }
                )
                
                await update.message.reply_text(
                    f"✅ **Scheduled Successfully!**\n"
                    f"at `{ist_time.strftime('%Y-%m-%d %I:%M %p')} IST`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                import traceback
                logging.error(f"Schedule Confirm Error: {e}", exc_info=True)
                await update.message.reply_text(f"❌ Error during schedule execution: {e}\n\nPlease try again or click Cancel.")
                # Return to confirm state so user can Cancel or Edit
                return MC_SCHEDULE_CONFIRM
                
            await admin_dashboard(update, context)
            return ConversationHandler.END
            
        return await cancel(update, context)
    except Exception as e:
        import traceback
        logging.error(f"Schedule Confirm Global Error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Critical Error in Confirm: {e}\n\nPlease try again or click Cancel.")
        return MC_SCHEDULE_CONFIRM



main_channel_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📢 Main Channel Post$"), start_main_channel_post)],
    states={
        MC_INPUT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_id)],
        MC_INPUT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_link)],
        MC_INPUT_NEWS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_news)],
        MC_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_action)],
        MC_SCHED_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_sched_date_input)],
        MC_SCHED_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_sched_time_input)],
        MC_SCHEDULE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_schedule_confirm)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ],
    allow_reentry=True
)
