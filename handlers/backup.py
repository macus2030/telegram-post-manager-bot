from telegram import Update
from telegram.ext import ContextTypes
from storage import DATA_FILE
from utils.helpers import check_admin, send_temp_message

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    try:
        await update.message.reply_document(
            document=open(DATA_FILE, 'rb'),
            caption="💾 **Backup Data**\n\nHere is your current data file. Keep it safe!"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting data: {e}")
        
# Future: Implement Import Data (Upload JSON)
# For now, simplistic export is sufficient for "Professional" requirement of "Backup"
