from telegram import Update
from telegram.ext import ContextTypes
from storage import DB_FILE
from utils.helpers import check_admin, send_temp_message

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    try:
        await update.message.reply_document(
            document=open(DB_FILE, 'rb'),
            caption="💾 **Backup Database**\n\nHere is your current `bot.db` file. Keep it safe!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting data: {e}")
        
# Future: Implement Import Data (Upload JSON)
# For now, simplistic export is sufficient for "Professional" requirement of "Backup"
