from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.constants import ParseMode
from storage import DB_FILE, lock
from utils.helpers import check_admin
import os

UPLOAD_DB, CONFIRM_RESTORE = range(2)

async def backup_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show options for Backup or Import."""
    if not check_admin(update.effective_user.id): return
    
    await update.message.reply_text(
        "💾 **Backup & Restore System**\n\n"
        "Select an option below:\n"
        "• **Download**: Get current data file.\n"
        "• **Restore**: Upload a previous backup to restore.",
        reply_markup=ReplyKeyboardMarkup([
            ["📥 Download Backup", "📤 Import / Restore"],
            ["🏠 Dashboard"]
        ], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the database file to the user."""
    # Logic extracted from previous export_data, now triggered by button
    if not check_admin(update.effective_user.id): return
    
    # Check if DB exists
    if not os.path.exists(DB_FILE):
         await update.message.reply_text("❌ No database file found.")
         return

    try:
        await update.message.reply_document(
            document=open(DB_FILE, 'rb'),
            caption="💾 **Backup Database**\n\nHere is your current `bot.db` file. Keep it safe!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting data: {e}")

# --- Import Conversation ---

async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    await update.message.reply_text(
        "📤 **Import / Restore Database**\n\n"
        "⚠️ **WARNING: This will overwite all current data!**\n\n"
        "Please upload your `bot.db` file now.",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return UPLOAD_DB

async def handle_db_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    
    # Validation
    if not doc.file_name.endswith('.db') and not doc.file_name.endswith('.sqlite'):
        await update.message.reply_text("❌ Invalid file. Please upload a `.db` file.")
        return UPLOAD_DB
        
    # Download header
    f = await doc.get_file()
    
    context.user_data['restore_file_id'] = f.file_id
    
    await update.message.reply_text(
        "⚠ **FINAL CONFIRMATION**\n\n"
        "Are you sure you want to replace the current database with this file?\n"
        "Current data will be LOST forever.",
        reply_markup=ReplyKeyboardMarkup([["✅ Yes, Restore Data", "❌ Cancel"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return CONFIRM_RESTORE

async def confirm_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text != "✅ Yes, Restore Data":
        await update.message.reply_text("❌ Restore cancelled.")
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    # Perform Restore
    file_id = context.user_data.get('restore_file_id')
    f_obj = await context.bot.get_file(file_id)
    
    msg = await update.message.reply_text("⏳ Restoring data...")
    
    try:
        with lock:
            # Download to temp
            temp_path = DB_FILE + ".restore_tmp"
            await f_obj.download_to_drive(temp_path)
            
            # Use os.replace for atomic-ish swap (Windows might be tricky with open locks, but we use lock)
            # We must ensure connections are closed? storage.lock should prevent NEW reads.
            # But get_connection opens local connections. 
            # If any other thread has DB open, this might fail on Windows.
            # We can try.
            
            import shutil
            shutil.move(temp_path, DB_FILE)
            
        await msg.edit_text("✅ **Restore Successful!**\n\nData has been updated.")
    except Exception as e:
        await msg.edit_text(f"❌ Restore Failed: {e}")
        
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Action cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

# Handler Definition
import_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📤 Import / Restore$"), start_import)],
    states={
        UPLOAD_DB: [MessageHandler(filters.Document.ALL, handle_db_upload)],
        CONFIRM_RESTORE: [MessageHandler(filters.Regex("^✅ Yes, Restore Data$"), confirm_restore)]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^❌ Cancel$"), cancel_import),
        MessageHandler(filters.Regex("^🏠 Dashboard$"), cancel_import) # Fallback to dash
    ],
    map_to_parent={
        # No parent, top level
    }
)
