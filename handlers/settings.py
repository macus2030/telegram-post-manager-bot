from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

from storage import get_message_template, update_message_template, get_help_link, update_help_link, get_main_template, update_main_template
from utils.helpers import check_admin
from config import HOW_TO_OPEN_LINK
from handlers.admin import MENU_REGEX, global_fallback, cancel

# States
SELECT_SETTING, EDIT_MSG_TEMPLATE, EDIT_HELP_LINK, EDIT_MAIN_TEMPLATE = range(4)

async def settings_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for Settings."""
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    return await show_settings_menu(update, context)

async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚙️ *Settings Menu*\n\n"
        "Select what you want to configure:\n"
        "• **Message Template**: The format of the message sent to users.\n"
        "• **Main Channel Template**: The format for channel posts.\n"
        "• **Help Link**: The 'How to Open' link."
    )
    
    kb = [
        ["📝 Edit Message Template", "📢 Edit Main Channel Template"],
        ["🔗 Edit Help Link", "🔙 Back to Dashboard"]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return SELECT_SETTING

async def handle_setting_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Back to Dashboard":
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    if text == "📝 Edit Message Template":
        current_template = get_message_template()
        await update.message.reply_text(
            "📝 *Edit Message Template*\n\n"
            "Current Template:\n"
            f"```\n{current_template}\n```\n\n"
            "**Available Variables**:\n"
            "`{post_id}` - Post ID\n"
            "`{caption}` - The caption text\n"
            "`{category}` - Category Name\n"
            "`{time}` - Auto-delete time (mins)\n"
            "`{link}` - Download/Watch Link\n"
            "`{how_to_open_link}` - Help Link\n\n"
            "Send the new template structure now:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_MSG_TEMPLATE
        
    if text == "🔗 Edit Help Link":
         current_link = get_help_link()
         await update.message.reply_text(
            "🔗 *Edit Help Link*\n\n"
            f"Current Link: `{current_link}`\n\n"
            "Send the new URL for the 'How to Open' link:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
             parse_mode="Markdown"
        )
         return EDIT_HELP_LINK
         
    if text == "📢 Edit Main Channel Template":
        current = get_main_template()
        await update.message.reply_text(
            "📢 *Edit Main Channel Template*\n\n"
            "Current Template:\n"
            f"```\n{current}\n```\n\n"
            "**Available Variables**:\n"
            "`{news}` - News/Content Text\n"
            "`{post_id}` - Post ID\n"
            "`{short_link}` - The link provided\n"
            "`{how_to_open_link}` - Help Link\n\n"
            "Send the new template structure now:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_MAIN_TEMPLATE

    await update.message.reply_text("Invalid selection.")
    return SELECT_SETTING

async def save_msg_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    update_message_template(text)
    await update.message.reply_text("✅ Message Template updated!", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def save_help_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
    
    link = text.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        link = f"https://{link}"

    update_help_link(link)
    await update.message.reply_text(f"✅ Help Link updated to:\n`{link}`", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def save_main_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    update_main_template(text)
    await update.message.reply_text("✅ Main Channel Template updated!", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

settings_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^⚙️ Settings$"), settings_dashboard)],
    states={
        SELECT_SETTING: [
            MessageHandler(filters.Regex("^📝 Edit Message Template$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔗 Edit Help Link$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔙 Back to Dashboard$"), handle_setting_selection)
        ],
        EDIT_MSG_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_msg_template)],
        EDIT_HELP_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_help_link)],
        EDIT_MAIN_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_main_template)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ],
    allow_reentry=True
)
