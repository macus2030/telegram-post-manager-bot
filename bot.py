import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, PicklePersistence
from config import TELEGRAM_TOKEN
import datetime

# Handlers will be imported here
from storage import get_pending_scheduled_posts, update_post
from handlers.admin import send_scheduled_post_job, execute_scheduled_post

# Robust Health Check Server for Render/UptimeRobot
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception:
            pass  # Ignore broken pipe errors

    def do_HEAD(self):
        try:
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
        except Exception:
            pass
    
    def log_message(self, format, *args):
        # Log health checks to debug UptimeRobot connection
        # Only log external IPs (not 127.0.0.1 which is Render internal)
        if self.client_address[0] != "127.0.0.1":
            print(f"Health Check PING from External: {self.client_address[0]}", flush=True)

def start_dummy_server():
    try:
        port = int(os.environ.get("PORT", 8080))
        # Bind to 0.0.0.0 to ensure external access
        server = ThreadingHTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"Health Check Server listening on port {port}", flush=True)
        server.serve_forever()
    except Exception as e:
        print(f"FATAL: Health Check Server Failed: {e}", flush=True)
        os._exit(1)

async def restore_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE):
    """Restore pending jobs from database on startup and watchdog."""
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
        image_id = data.get("main_channel_photo_id")
        
        if not target_chat_id or not preview_text:
            logging.warning(f"Post #{pid} missing schedule data (chat_id or text). Skipping.")
            continue
            
        # Calculate delay
        delay = scheduled_for - now
        
        # Check if already scheduled in JobQueue to avoid duplicates
        existing_jobs = context.job_queue.get_jobs_by_name(f"sched_{pid}")
        if existing_jobs:
            continue

        # If passed?
        if delay < 0:
            logging.warning(f"Post #{pid} schedule time passed ({delay}s ago). Attempting to send immediately...")
            # Execute Immediately
            success = await execute_scheduled_post(context, str(pid), target_chat_id, preview_text, image_id)
            if success:
                 count += 1
            else:
                 logging.error(f"Failed to recover missed post #{pid}")
            continue
            
        # Re-schedule
        context.job_queue.run_once(
            send_scheduled_post_job, 
            delay,
            chat_id=target_chat_id,
            name=f"sched_{pid}",
            data={
                "chat_id": target_chat_id,
                "text": preview_text,
                "post_id": str(pid),
                "image_id": image_id
            }
        )
        count += 1
        
    if count > 0:
        logging.info(f"🔄 Restored/Recovered {count} scheduled posts.")

async def schedule_watchdog(context: ContextTypes.DEFAULT_TYPE):
    """Periodic check for missed schedules."""
    await restore_scheduled_jobs(context)

async def auto_backup_job(context: ContextTypes.DEFAULT_TYPE):
    """Send database backup to admin automatically and optionally forward to a channel."""
    from config import ADMIN_ID, BACKUP_CHANNEL_ID
    from storage import DB_FILE
    import os
    
    if not os.path.exists(DB_FILE):
        logging.warning(f"Auto-backup skipped: {DB_FILE} not found")
        return
    
    backup_sent = False
    
    # Send to Admin
    if ADMIN_ID and ADMIN_ID != 0:
        try:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=open(DB_FILE, 'rb'),
                caption=f"🔄 **Auto-Backup (Admin)**\n\n"
                        f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"💾 Database Backup",
                parse_mode="Markdown",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=120
            )
            logging.info("✅ Auto-backup sent to admin successfully")
            backup_sent = True
        except Exception as e:
            logging.error(f"❌ Auto-backup to Admin failed: {e}")
            
    # Forward to Channel
    if BACKUP_CHANNEL_ID:
        try:
            await context.bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=open(DB_FILE, 'rb'),
                caption=f"🔄 **Auto-Backup (Archive)**\n\n"
                        f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"💾 Partial/Full Dump",
                parse_mode="Markdown",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=120
            )
            logging.info(f"✅ Auto-backup forwarded to channel {BACKUP_CHANNEL_ID}")
            backup_sent = True
        except Exception as e:
            logging.error(f"❌ Auto-backup to Channel failed: {e}")

    if not backup_sent:
        logging.warning("Auto-backup generated but no destination configured (Admin or Channel missing)")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logging.error(f"Exception while handling an update: {context.error}", exc_info=True)

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
        # Run restore once
        await restore_scheduled_jobs(app) # context is compatible with app for some operations, but restore_scheduled_jobs needs context.job_queue which app has.
        # Wait, context object vs application object.
        # send_scheduled_post_job takes context.
        # app.job_queue.run_once takes callback(context).
        
        # restore_scheduled_jobs uses context.job_queue.
        # application object has job_queue.
        # But 'context' in job callback has job_queue too.
        # Let's just use 'app' as 'context' where compatible, or rewrite restore to accept app.
        # Actually, let's keep restore_scheduled_jobs expecting something with .job_queue and .bot
        
        # Schedule watchdog
        app.job_queue.run_repeating(schedule_watchdog, interval=60, first=10)
        
        # Auto-backup: Run once on startup (after 30 sec) and then at configured interval
        from storage import get_backup_interval
        backup_hours = get_backup_interval()
        backup_seconds = backup_hours * 3600  # Convert hours to seconds
        
        app.job_queue.run_once(auto_backup_job, when=30, name="startup_backup")
        app.job_queue.run_repeating(auto_backup_job, interval=backup_seconds, first=backup_seconds, name="daily_backup")
        logging.info(f"🔄 Auto-backup scheduled: Startup + Every {backup_hours} hours")

        
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).persistence(persistence).post_init(post_init).build()

    # Register Handlers
    from handlers.admin import create_post_conv, admin_dashboard, clear_chat_history, main_channel_conv, scheduled_dashboard, sched_edit_conv, handle_schedule_callback, migrate_passwords_command
    from handlers.user import start_user, handle_not_joined, handle_password_callback, handle_preview_callback
    from handlers.manager import post_manager, handle_manager_callback, edit_post_conv
    from handlers.stats import stats_dashboard
    from handlers.bulk import bulk_conv
    from handlers.backup import export_data, backup_menu, import_conv
    from handlers.search import search_conv

    from handlers.categories import category_conv
    from handlers.settings import settings_conv, settings_dashboard
    from handlers.users_admin import users_dashboard, user_search_conv, handle_users_callback
    from handlers.broadcast import broadcast_dashboard, broadcast_conv, handle_bc_callback
    
    # Conversations first
    application.add_handler(settings_conv)
    application.add_handler(category_conv)
    application.add_handler(create_post_conv)
    application.add_handler(main_channel_conv)
    application.add_handler(bulk_conv)
    application.add_handler(search_conv)
    application.add_handler(edit_post_conv)
    application.add_handler(sched_edit_conv)
    application.add_handler(broadcast_conv)
    application.add_handler(user_search_conv)
    application.add_handler(import_conv) # Backup/Restore

    # Callbacks
    application.add_handler(CallbackQueryHandler(handle_not_joined, pattern="^check_sub_"))
    application.add_handler(CallbackQueryHandler(handle_password_callback, pattern="^pass_"))
    application.add_handler(CallbackQueryHandler(handle_schedule_callback, pattern="^sched_"))
    application.add_handler(CallbackQueryHandler(handle_preview_callback, pattern="^view_preview_"))
    application.add_handler(CallbackQueryHandler(handle_users_callback, pattern="^(users_|search_user|ban_|unban_|back_users)"))
    application.add_handler(CallbackQueryHandler(handle_bc_callback, pattern="^bc_"))
    application.add_handler(CallbackQueryHandler(handle_manager_callback, pattern="^(?!cat_|add_new_category|back_to_dashboard|check_sub_|sched_|users_|search_user|ban_|unban_|bc_|view_preview_).*")) 
    # Old category callbacks are no longer needed as we use ReplyKeyboard, but keeping pattern exclusion in manager is fine.
    
    # Commands
    application.add_handler(CommandHandler("start", start_user))
    application.add_handler(CommandHandler("migrate_passwords", migrate_passwords_command))
    
    # Admin Menu Buttons
    application.add_handler(MessageHandler(filters.Regex("^🏠 Dashboard$"), admin_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^📝 Post Manager$"), post_manager))
    # Categories button is now handled by category_conv entry point
    
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Settings$"), settings_dashboard))

    application.add_handler(MessageHandler(filters.Regex("^📊 Statistics$"), stats_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^💾 Backup & Export$"), backup_menu))
    application.add_handler(MessageHandler(filters.Regex("^📥 Download Backup$"), export_data))
    application.add_handler(MessageHandler(filters.Regex("^🧹 Clear Chat$"), clear_chat_history))
    application.add_handler(MessageHandler(filters.Regex("^⏳ Scheduled Posts$"), scheduled_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^👥 Users$"), users_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^📢 Broadcast$"), broadcast_dashboard))
    application.add_handler(MessageHandler(filters.Regex("^🔙 Back$"), admin_dashboard))
    
    # Catch-all for dashboard
    application.add_handler(MessageHandler(filters.Regex("^(🏠 Dashboard|🔙 Back)$"), admin_dashboard))  

    application.add_error_handler(error_handler)

    # Start Dummy Server in Background Thread
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()

    print("Bot started...", flush=True)
    try:
        application.run_polling()
    except Exception as e:
        print(f"FATAL: Polling Error: {e}", flush=True)
        # Keep process alive if needed or exit?
        raise e

if __name__ == '__main__':
    try:
        # Override print to always flush? Or just use flush=True manually
        print("Starting Bot Process...", flush=True)
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"FATAL: Main Process Crashed: {e}", flush=True)
