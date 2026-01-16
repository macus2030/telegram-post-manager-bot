import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import TELEGRAM_TOKEN
# Handlers will be imported here
# from handlers import admin, user

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to start the bot."""
    await update.message.reply_text("Bot is running! 🚀")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logging.error(f"Exception while handling an update: {context.error}")

def main():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not found in .env")
        return

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Register Handlers
    from handlers.admin import create_post_conv, admin_dashboard, clear_chat_history
    from handlers.user import start_user
    from handlers.manager import post_manager, handle_manager_callback, edit_post_conv
    from handlers.stats import stats_dashboard
    from handlers.bulk import bulk_conv
    from handlers.backup import export_data
    from handlers.search import search_conv
    
    # Conversations first
    application.add_handler(create_post_conv)
    application.add_handler(bulk_conv)
    application.add_handler(search_conv)
    application.add_handler(edit_post_conv)

    # Callbacks
    application.add_handler(CallbackQueryHandler(handle_manager_callback))
    
    # Commands
    application.add_handler(CommandHandler("start", start_user))
    
    # Admin Menu Buttons
    application.add_handler(MessageHandler(filters.Regex("^🏠 Dashboard$"), admin_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^📝 Post Manager$"), post_manager))
    application.add_handler(MessageHandler(filters.Regex("^📊 Statistics$"), stats_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^💾 Backup & Export$"), export_data))
    application.add_handler(MessageHandler(filters.Regex("^🧹 Clear Chat$"), clear_chat_history))
    application.add_handler(MessageHandler(filters.Regex("^🔙 Back$"), admin_dashboard))
    
    # Catch-all for dashboard
    application.add_handler(MessageHandler(filters.Regex("^(🏠 Dashboard|🔙 Back)$"), admin_dashboard))  

    application.add_error_handler(error_handler)

    print("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
