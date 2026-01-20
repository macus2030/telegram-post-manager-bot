from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from telegram.constants import ParseMode
from storage import get_all_users_count, ban_user, unban_user, is_banned, add_user, get_connection
from utils.helpers import check_admin
import time
import datetime

# States for search
SEARCH_USER_INPUT = range(1)

async def users_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    count = get_all_users_count()
    
    text = (
        "👥 *User Management*\n\n"
        f"Total Users: `{count}`\n\n"
        "Select an action:"
    )
    
    kb = [
        [InlineKeyboardButton("🔍 Search User", callback_data="search_user_start")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="users_dashboard_return")]
    ]
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def start_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "🔍 *Search User*\n\n"
        "Please send the **User ID** to look up.",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
    )
    return SEARCH_USER_INPUT

async def perform_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        await update.message.reply_text("❌ Cancelled.")
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context) # Or users_dashboard
        return ConversationHandler.END
        
    if not text.isdigit():
        await update.message.reply_text("⚠ Invalid ID. Please enter numeric User ID.")
        return SEARCH_USER_INPUT
        
    user_id = int(text)
    
    # Get info
    # We might not have full info if they never started bot but are in DB?
    # Our DB `users` table has basic info.
    # Let's check status
    banned = is_banned(user_id)
    
    # Try to see if we have joined info
    # Manually query DB for joined_at
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT joined_at, username FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        await update.message.reply_text(f"❌ User ID `{user_id}` not found in database.")
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    joined_at = row[0]
    username = row[1] or "Unknown"
    join_date = datetime.datetime.fromtimestamp(joined_at).strftime('%Y-%m-%d %H:%M')
    
    status_icon = "🚫 BANNED" if banned else "✅ Active"
    
    import html
    safe_username = html.escape(username)
    
    msg = (
        f"👤 <b>User Profile</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{safe_username}\n"
        f"📅 Joined: {join_date}\n"
        f"abc Status: {status_icon}"
    )
    
    kb = []
    if banned:
        kb.append([InlineKeyboardButton("✅ Unban User", callback_data=f"unban_{user_id}")])
    else:
        kb.append([InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{user_id}")])
        
    kb.append([InlineKeyboardButton("🔙 Back to Users", callback_data="back_users_dash")])
    
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def handle_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data == "users_dashboard_return":
        await query.message.delete()
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return
        
    if data == "back_users_dash":
        await users_dashboard(update, context)
        return
        
    if data.startswith("ban_"):
        uid = int(data.split("_")[1])
        ban_user(uid)
        await query.answer("🚫 User Banned")
        # Refresh view?
        # We need to act as if we searched again.
        # Cheap way: Edit message
        await query.edit_message_caption(caption="🚫 User was BANNED.") # If it was a photo? No text.
        # Just re-send search dashboard
        await users_dashboard(update, context)
        
    if data.startswith("unban_"):
        uid = int(data.split("_")[1])
        unban_user(uid)
        await query.answer("✅ User Unbanned")
        await users_dashboard(update, context)

user_search_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_search_user, pattern="^search_user_start$")],
    states={
        SEARCH_USER_INPUT: [MessageHandler(filters.TEXT, perform_user_search)]
    },
    fallbacks=[CommandHandler("cancel", perform_user_search)] # Reusing cancel logic
)
