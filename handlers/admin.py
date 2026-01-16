from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
from config import ADMIN_ID
from storage import add_post, save_template, get_templates
from utils.helpers import send_temp_message, show_loading, escape_markdown_v2, check_admin
import time

# States
SELECT_TYPE, UPLOAD_FILE, INPUT_LINK, EDIT_CAPTION, SELECT_CATEGORY, CONFIRM = range(6)

# Keyboards
DASHBOARD_KB = [
    ["➕ Create Post", "📦 Bulk Create"],
    ["📝 Post Manager", "📊 Statistics"],
    ["💾 Backup & Export", "🔍 Search"],
    ["🧹 Clear Chat"]
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
        await update.message.reply_text("Please choose a valid option.")
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
        
    context.user_data['caption'] = msg.caption or "Check this out! 👇"
    
    await update.message.reply_text("✅ File received!")
    return await ask_edit_caption(update, context)

async def handle_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    # Basic validation
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("⚠ Invalid URL. Please include http:// or https://")
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
    
    kb = [["✅ Keep Current"], ["❌ Cancel"]]
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
        
    if text != "✅ Keep Current":
        context.user_data['caption'] = text
        await send_temp_message(context, update.effective_chat.id, "✅ Caption updated!", delay=3)
        
    # Proceed to Category
    categories = ["😂 Comedy", "😱 Horror", "🔥 Action", "❤️ Romance", "🎓 Edu", "🎵 Music", "❌ Skip"]
    kb = []
    row = []
    for cat in categories:
        row.append(cat)
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    await update.message.reply_text(
        "🏷 *Select Category*",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECT_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = update.message.text
    if cat == "❌ Cancel": # Just in case
        return await cancel(update, context)

    context.user_data['category'] = cat.replace("❌ Skip", "Uncategorized").split(" ")[-1] # Remove emoji
    
    return await show_final_confirmation(update, context)

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
    
    success_msg = (
        f"✅ *Post Created Successfully!* (#{post_id})\n\n"
        f"🔗 *Deep Link*:\n`{deep_link}`\n\n"
        f"Status: {status}"
    )
    
    await update.message.reply_text(success_msg, parse_mode=ParseMode.MARKDOWN)
    
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
        SELECT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_type)],
        UPLOAD_FILE: [MessageHandler(filters.ATTACHMENT | filters.VIDEO | filters.PHOTO | filters.AUDIO | filters.Document.ALL, handle_file_upload)],
        INPUT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link_input)],
        EDIT_CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_caption)],
        SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_category)],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, final_confirm)]
    },
    fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^❌ Cancel$"), cancel)]
)
