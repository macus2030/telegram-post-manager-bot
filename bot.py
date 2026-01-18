import logging
import os
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, PicklePersistence

import datetime

from config import TELEGRAM_TOKEN

# Dummy Server for Render Binding
def start_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    handler = SimpleHTTPRequestHandler
    with TCPServer(("", port), handler) as httpd:
        print(f"Dummy server executing on port {port}")
        httpd.serve_forever()

# Handlers will be imported here
# from handlers import admin, user
from storage import get_pending_scheduled_posts, update_post
from handlers.admin import send_scheduled_post_job

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

async def restore_scheduled_jobs(application):
    """Restore pending jobs from database on startup."""
    posts = get_pending_scheduled_posts()
    count = 0
    now = datetime.datetime.now().timestamp()
    
    for pid, data in posts:
        # Check if actually scheduled
        if not data.get("is_scheduled"):
            continue
            
        scheduled_for = data.get("scheduled_for")
        if not scheduled_for:
            continue
            
        target_chat_id = data.get("target_chat_id")
        preview_text = data.get("channel_preview_text")
        
        if not target_chat_id or not preview_text:
            logging.warning(f"Post #{pid} missing schedule data. Skipping.")
            continue
            
        # Calculate delay
        delay = scheduled_for - now
        
        # If passed?
        if delay < 0:
            logging.warning(f"Post #{pid} schedule time passed. Marking failed.")
            update_post(str(pid), {"status": "failed", "is_scheduled": False, "note": "Missed schedule during downtime."})
            continue
            
        # Re-schedule
        application.job_queue.run_once(
            send_scheduled_post_job, 
            delay,
            chat_id=target_chat_id,
            name=f"sched_{pid}",
            data={
                "chat_id": target_chat_id,
                "text": preview_text,
                "post_id": str(pid)
            }
        )
        count += 1
        
    if count > 0:
        print(f"🔄 Restored {count} scheduled posts.")

def main():
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not found in .env")
        return

    if os.path.exists("/data"):
        persistence_path = "/data/bot_datastore"
    else:
        persistence_path = "bot_datastore"
        
    persistence = PicklePersistence(filepath=persistence_path)
    
    # Restore scheduled jobs
    # We need to run this async, but application.run_polling() blocks.
    # We can use post_init
    async def post_init(app):
        await restore_scheduled_jobs(app)
        
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).persistence(persistence).post_init(post_init).build()

    # Register Handlers
    from handlers.admin import create_post_conv, admin_dashboard, clear_chat_history, main_channel_conv, scheduled_dashboard
    from handlers.user import start_user, handle_not_joined
    from handlers.manager import post_manager, handle_manager_callback, edit_post_conv
    from handlers.stats import stats_dashboard
    from handlers.bulk import bulk_conv
    from handlers.backup import export_data
    from handlers.search import search_conv

    from handlers.categories import category_conv
    from handlers.settings import settings_conv, settings_dashboard
    
    # Conversations first
    application.add_handler(settings_conv)
    application.add_handler(category_conv)
    application.add_handler(create_post_conv)
    application.add_handler(main_channel_conv)
    application.add_handler(bulk_conv)
    application.add_handler(search_conv)
    application.add_handler(edit_post_conv)

    # Callbacks
    application.add_handler(CallbackQueryHandler(handle_not_joined, pattern="^check_sub_"))
    application.add_handler(CallbackQueryHandler(handle_manager_callback, pattern="^(?!cat_|add_new_category|back_to_dashboard|check_sub_).*")) 
    # Old category callbacks are no longer needed as we use ReplyKeyboard, but keeping pattern exclusion in manager is fine.
    
    # Commands
    application.add_handler(CommandHandler("start", start_user))
    
    # Admin Menu Buttons
    application.add_handler(MessageHandler(filters.Regex("^🏠 Dashboard$"), admin_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^📝 Post Manager$"), post_manager))
    # Categories button is now handled by category_conv entry point
    
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Settings$"), settings_dashboard))

    application.add_handler(MessageHandler(filters.Regex("^📊 Statistics$"), stats_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^💾 Backup & Export$"), export_data))
    application.add_handler(MessageHandler(filters.Regex("^🧹 Clear Chat$"), clear_chat_history))
    application.add_handler(MessageHandler(filters.Regex("^⏳ Scheduled Posts$"), scheduled_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^🔙 Back$"), admin_dashboard))
    
    # Catch-all for dashboard
    application.add_handler(MessageHandler(filters.Regex("^(🏠 Dashboard|🔙 Back)$"), admin_dashboard))  

    application.add_error_handler(error_handler)

    # Start Dummy Server in Background Thread
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()

    print("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
