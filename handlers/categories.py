from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

from storage import get_categories, add_category, update_category, delete_category
from utils.helpers import check_admin, send_temp_message

# Conversation States
SELECT_CATEGORY, CATEGORY_ACTIONS, ADD_CATEGORY, EDIT_CATEGORY_NAME = range(4)

# Helper to find ID by name (since Reply Buttons send text)
def get_cat_id_by_name(name: str):
    categories = get_categories()
    for cid, data in categories.items():
        if data['name'] == name:
            return cid
    return None

async def category_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: Shows list of categories in Reply Keyboard."""
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    return await show_category_list(update, context)

async def show_category_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = get_categories()
    
    # Text explanation
    text = "📂 *Category Manager*\n\nSelect a category to manage, or add a new one."
    
    # Build Reply Keyboard
    kb = [["➕ Add New Category"]]
    
    # Categories rows
    row = []
    for cat in categories.values():
        row.append(f"🏷 {cat['name']}")
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append(["🔙 Back to Dashboard"])
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return SELECT_CATEGORY

async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Back to Dashboard":
        # Import here to avoid circular dependency if possible, or use end signal
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    if text == "➕ Add New Category":
        await update.message.reply_text(
            "➕ *Add New Category*\n\nPlease send the name for the new category:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ADD_CATEGORY

    # Check if valid category
    cat_name = text.replace("🏷 ", "")
    cat_id = get_cat_id_by_name(cat_name)
    
    if not cat_id:
        await update.message.reply_text("❌ Category not found. Please select from the menu.")
        return SELECT_CATEGORY
        
    context.user_data['selected_cat_id'] = cat_id
    context.user_data['selected_cat_name'] = cat_name
    
    # Show Actions Menu
    await update.message.reply_text(
        f"🏷 Selected: *{cat_name}*\n\nChoose an action:",
        reply_markup=ReplyKeyboardMarkup([["✏️ Edit Name", "🗑 Delete"], ["🔙 Back"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CATEGORY_ACTIONS

async def action_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await show_category_list(update, context)

async def action_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_id = context.user_data.get('selected_cat_id')
    cat_name = context.user_data.get('selected_cat_name')
    delete_category(cat_id)
    await update.message.reply_text(f"✅ Category *{cat_name}* deleted!", parse_mode="Markdown")
    return await show_category_list(update, context)

async def action_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_name = context.user_data.get('selected_cat_name')
    await update.message.reply_text(
        f"✏️ *Editing: {cat_name}*\n\nSend the new name:",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return EDIT_CATEGORY_NAME

async def action_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚠ Please select a valid action (Edit, Delete, Back) or click Dashboard.")
    return CATEGORY_ACTIONS

async def save_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    if name == "❌ Cancel":
        return await show_category_list(update, context)
        
    add_category(name)
    await update.message.reply_text(f"✅ Category *{name}* added!", parse_mode="Markdown")
    return await show_category_list(update, context)

async def save_edit_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    if name == "❌ Cancel":
        # Return to actions menu
        cat_name = context.user_data.get('selected_cat_name')
        await update.message.reply_text(
            f"🏷 Selected: *{cat_name}*\n\nChoose an action:",
            reply_markup=ReplyKeyboardMarkup([["✏️ Edit Name", "🗑 Delete"], ["🔙 Back"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return CATEGORY_ACTIONS
        
    cat_id = context.user_data.get('selected_cat_id')
    update_category(cat_id, name)
    
    # Update context name
    context.user_data['selected_cat_name'] = name
    
    await update.message.reply_text(f"✅ Renamed to *{name}*!", parse_mode="Markdown")
    
    # Return to actions
    await update.message.reply_text(
        f"🏷 Selected: *{name}*\n\nChoose an action:",
        reply_markup=ReplyKeyboardMarkup([["✏️ Edit Name", "🗑 Delete"], ["🔙 Back"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return CATEGORY_ACTIONS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

from handlers.admin import MENU_REGEX, global_fallback

# Single Unified Conversation Handler
category_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📂 Categories$"), category_dashboard)],
    states={
        SELECT_CATEGORY: [
            MessageHandler(filters.Regex("^➕ Add New Category$"), handle_category_selection),
            MessageHandler(filters.Regex("^🔙 Back to Dashboard$"), handle_category_selection),
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), handle_category_selection)
        ],
        CATEGORY_ACTIONS: [
            MessageHandler(filters.Regex(r"Edit Name"), action_edit),
            MessageHandler(filters.Regex(r"Delete"), action_delete),
            MessageHandler(filters.Regex(r"Back"), action_back),
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), action_invalid)
        ],
        ADD_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_new_category)],
        EDIT_CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_edit_category)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ]
)
