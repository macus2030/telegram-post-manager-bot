from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
import html
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from config import ADMIN_ID, AUTO_DELETE_SECONDS, MAIN_CHANNEL_ID
from storage import add_post, save_template, get_templates, get_message_template, get_help_link, get_post, get_main_template, update_post, get_latest_post_id
from utils.helpers import send_temp_message, show_loading, escape_markdown_v2, check_admin, validate_link
import time

# States
SELECT_TYPE, UPLOAD_FILE, INPUT_LINK, EDIT_CAPTION, INPUT_PASSWORD, SELECT_CATEGORY, CONFIRM = range(7)
# Main Channel Flow States
MC_INPUT_ID, MC_INPUT_LINK, MC_INPUT_NEWS, MC_CONFIRM, MC_SCHEDULE = range(6, 11)

# Keyboards
DASHBOARD_KB = [
    ["➕ Create Post", "📦 Bulk Create"],
    ["📢 Main Channel Post", "📝 Post Manager"],
    ["📂 Categories", "📊 Statistics"],
    ["⚙️ Settings", "💾 Backup & Export"],
    ["🔍 Search", "🧹 Clear Chat"]
]

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    text = (
        "🏠 *Admin Dashboard*\n\n"
        "Select an action below:"
    )
    markup = ReplyKeyboardMarkup(DASHBOARD_KB, resize_keyboard=True)
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

    elif text == "➕ Create Post":
         await update.message.reply_text("🔄 Switching modes... Please click **Create Post** again.", parse_mode="Markdown")
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

    elif text == "🧹 Clear Chat":
        await clear_chat_history(update, context)
        return ConversationHandler.END
        
    elif text == "❌ Cancel":
        return await cancel(update, context)
        
    return await cancel(update, context) # Default

# Regex for all menu buttons
MENU_REGEX = "^(🏠 Dashboard|📝 Post Manager|📂 Categories|⚙️ Settings|📊 Statistics|💾 Backup & Export|🧹 Clear Chat|❌ Cancel|➕ Create Post|📦 Bulk Create|📢 Main Channel Post|🔍 Search)$"

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
        return await show_final_confirmation(update, context)

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
    data = context.user_data
    
    preview_text = (
        "📋 *Confirm Post Creation*\n\n"
        f"**Type**: {data.get('type')}\n"
        f"**Category**: {data.get('category')}\n"
        f"**File**: {data.get('file_name', 'N/A')}\n"
        f"**Link**: {data.get('link', 'N/A')}\n\n"
        "**Caption/Content**:\n"
        f"_{data.get('caption')}_"
    )
    
    kb = [["✅ Create Post", "Draft Mode"], ["✏️ Edit Again", "❌ Cancel"]]
    await update.message.reply_text(
        preview_text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM

async def final_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "❌ Cancel":
        return await cancel(update, context)
        
    if choice == "✏️ Edit Again":
        return await ask_edit_caption(update, context)
    
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
        # Default empty fields
        "tags": [],
        "views": 0,
        "note": ""
    })
    
    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start={post_id}"
    
    # Render Preview
    template = get_message_template()
    post_link = data.get('link') or ""
    
    import re
    if not post_link:
        # Magic: If link is empty, remove related header line
        template = re.sub(r"(?i)^.*(Download/Watch Link|Link👇).*$\n?", "", template, flags=re.MULTILINE)
    
    variables = {
        "post_id": post_id,
        "caption": data['caption'],
        "category": data['category'],
        "time": int(AUTO_DELETE_SECONDS/60),
        "link": post_link,
        "how_to_open_link": get_help_link()
    }
    
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
    
    # Loop backwards
    n = 0
    for mid in range(message_id, message_id - 50, -1):
        try:
            await context.bot.delete_message(chat_id, mid)
            n += 1
        except Exception:
            pass # Ignore errors (already deleted, too old, etc)
    
    # Also delete the status message itself if possible, but we just re-dashboard
    await admin_dashboard(update, context)

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
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), final_confirm)]
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
    bot_username = context.bot.username
    deep_link = f"https://t.me/{bot_username}?start={post_id}"
    context.user_data['mc_deep_link'] = deep_link
    
    await update.message.reply_text(
        f"✅ Validated Post #{post_id}\n\n"
        f"🔗 **Deep Link**:\n`{deep_link}`\n\n"
        "Please send the **Shortened Link** (or any link) you want to use.\n"
        "Send 'skip' to use the raw deep link.",
        parse_mode=ParseMode.MARKDOWN
    )
    return MC_INPUT_LINK

async def mc_input_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    if text.lower() == 'skip':
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
        parse_mode=ParseMode.MARKDOWN
    )
    return MC_INPUT_NEWS

async def mc_input_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    # Auto-apply strikethrough as requested
    escaped_text = html.escape(text)
    context.user_data['mc_news'] = f"<s>{escaped_text}</s>"
    return await mc_render_preview(update, context)

async def mc_render_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Prepare variables
    data = context.user_data
    variables = {
        "post_id": data['mc_post_id'],
        "short_link": data['mc_short_link'],
        "news": data['mc_news'],
        "how_to_open_link": get_help_link()
    }
    
    template = get_main_template()
    
    # Validation
    missing = []
    import string
    # Get field names from template
    required_keys = [t[1] for t in string.Formatter().parse(template) if t[1] is not None]
    
    for key in required_keys:
        if key not in variables:
            missing.append(key)
            
    if missing:
        await update.message.reply_text(
            f"❌ Template Error: The following placeholders are missing data: {', '.join(missing)}\n"
            "Please check your template or inputs."
        )
        return MC_INPUT_NEWS # Ask for news again? Or just Stuck? Let's go back to News or Dashboard.
        # Actually, variables come from previous steps. Only way to fix is ensuring code provides them.
        # Since I hardcoded valid variables, this detects if user Added custom keys in template.
        
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
            "Enter delay in **minutes** (e.g., `10`, `60`)\n"
            "OR time in `HH:MM` format (24h, future time today).",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return MC_SCHEDULE

    return MC_CONFIRM

async def send_scheduled_post_job(context: ContextTypes.DEFAULT_TYPE):
    """Job to send the scheduled post."""
    job = context.job
    data = job.data
    
    chat_id = data['chat_id']
    text = data['text']
    post_id = data['post_id']
    
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
            "scheduled_for": None
        })
        print(f"Scheduled Post #{post_id} sent successfully.")
        
    except Exception as e:
        print(f"Failed to send scheduled post #{post_id}: {e}")

async def mc_schedule_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel": return await cancel(update, context)
    
    if text == "✅ Yes, Schedule":
         await update.message.reply_text("Enter time:")
         return MC_SCHEDULE
         
    import datetime
    delay_seconds = 0
    
    try:
        # Try minutes integer
        if text.isdigit():
            mins = int(text)
            delay_seconds = mins * 60
        elif ":" in text:
            # HH:MM Parsing
            now = datetime.datetime.now()
            target_time = datetime.datetime.strptime(text, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if target_time < now:
                await update.message.reply_text("⚠ Time passed. Please use future time.")
                return MC_SCHEDULE
            delay_seconds = (target_time - now).total_seconds()
        else:
            raise ValueError("Invalid format")
            
        if delay_seconds <= 0:
             await update.message.reply_text("⚠ Invalid time.")
             return MC_SCHEDULE

        # Schedule Job
        post_id = context.user_data['mc_post_id']
        preview_text = context.user_data['mc_preview_text']
        
        # Calculate Future Time
        # delay_seconds is calculated above.
        # We need datetime object for schedule_date
        # Ensure it is timezone aware or UTC? PTB usually handles naive as local or UTC.
        # Best to use delay_seconds to add to NOW.
        
        schedule_time = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)
        
        # IST Conversion (UTC + 5:30)
        ist_time = schedule_time + datetime.timedelta(hours=5, minutes=30)
        
        try:
            # Use JobQueue instead of schedule_date
            context.job_queue.run_once(
                send_scheduled_post_job, 
                delay_seconds,
                chat_id=MAIN_CHANNEL_ID,
                name=f"sched_{post_id}",
                data={
                    "chat_id": MAIN_CHANNEL_ID,
                    "text": preview_text,
                    "post_id": post_id
                }
            )
            
            # Update DB
            update_post(post_id, {
                "posted_to_channel": False, # Not yet
                "is_scheduled": True,
                "scheduled_for": int(schedule_time.timestamp())
            })
            
            await update.message.reply_text(
                f"✅ **Successfully Scheduled!**\n\n"
                f"Post #{post_id} will be sent to the channel at:\n"
                f"`{ist_time.strftime('%Y-%m-%d %H:%M:%S')} (IST)`\n\n"
                "_(Buffered by Bot Persistence)_",
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
             await update.message.reply_text(f"❌ Failed to schedule: {e}")
             return MC_SCHEDULE
        
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Use Minutes (int) or HH:MM.")
        return MC_SCHEDULE



main_channel_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📢 Main Channel Post$"), start_main_channel_post)],
    states={
        MC_INPUT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_id)],
        MC_INPUT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_link)],
        MC_INPUT_NEWS: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_input_news)],
        MC_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_action)],
        MC_SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), mc_schedule_input)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ],
    allow_reentry=True
)
