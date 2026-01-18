from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CallbackQueryHandler, CommandHandler, filters
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest
import logging
import asyncio
from storage import get_all_users_count, get_all_users_iter
from utils.helpers import check_admin

# States
INPUT_MSG, CONFIRM_BROADCAST = range(2)

async def broadcast_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    user_count = get_all_users_count()
    
    text = (
        "📢 *Broadcast Manager*\n\n"
        f"👥 Total Users: `{user_count}`\n\n"
        "Send a message to all users of the bot. "
        "Supports Text, Photo, Video, Document, etc."
    )
    
    kb = [
        [InlineKeyboardButton("📨 New Broadcast", callback_data="start_broadcast")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="bc_dashboard_return")]
    ]
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "📨 *New Broadcast*\n\n"
        "Please send the message you want to broadcast (Text, Image, Video, etc.).\n"
        "Or /cancel to stop.",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
    )
    return INPUT_MSG

async def handle_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.text == "❌ Cancel":
        await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    # Store message object to copy
    # We can store message_id and chat_id to copy_message
    context.user_data['broadcast_msg_id'] = msg.message_id
    context.user_data['broadcast_chat_id'] = msg.chat_id
    
    # Show preview confirm
    await msg.reply_text(
        "✅ Message recieved!\n\n"
        "Are you sure you want to send this to ALL users?",
        reply_markup=ReplyKeyboardMarkup([["✅ Confirm Send", "❌ Cancel"]], resize_keyboard=True)
    )
    return CONFIRM_BROADCAST

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text != "✅ Confirm Send":
        await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
        
    # Start Background Task
    await update.message.reply_text("🚀 Broadcast started! You will be notified when done.", reply_markup=ReplyKeyboardRemove())
    
    # Get IDs
    msg_id = context.user_data['broadcast_msg_id']
    from_chat = context.user_data['broadcast_chat_id']
    
    context.application.create_task(run_broadcast(context, from_chat, msg_id, update.effective_user.id))
    
    return ConversationHandler.END

async def run_broadcast(context, from_chat, msg_id, admin_id):
    success = 0
    blocked = 0
    failed = 0
    
    start_time = asyncio.get_running_loop().time()
    
    try:
        # Iterate users
        async for user_id in async_user_iter():
            try:
                await context.bot.copy_message(chat_id=user_id, from_chat_id=from_chat, message_id=msg_id)
                success += 1
            except Forbidden:
                blocked += 1
                # Mark as blocked/banned in DB? maybe later
            except Exception as e:
                failed += 1
                
            # Rate limit protection
            if success % 20 == 0:
                await asyncio.sleep(1)
                
        duration = asyncio.get_running_loop().time() - start_time
        
        report = (
            "📢 *Broadcast Complete*\n\n"
            f"✅ Success: {success}\n"
            f"🚫 Blocked: {blocked}\n"
            f"❌ Failed: {failed}\n"
            f"⏱ Duration: {int(duration)}s"
        )
        
        await context.bot.send_message(chat_id=admin_id, text=report, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logging.error(f"Broadcast error: {e}")
        await context.bot.send_message(chat_id=admin_id, text=f"⚠ Broadcast failed error: {e}")

# Helper to wrap sync generator
async def async_user_iter():
    for uid in get_all_users_iter():
        yield uid
        await asyncio.sleep(0.01) # Yield to event loop

async def cancel_bc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

broadcast_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_broadcast, pattern="^start_broadcast$")],
    states={
        INPUT_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.Regex("^❌ Cancel$"), handle_broadcast_input)],
        CONFIRM_BROADCAST: [MessageHandler(filters.TEXT, confirm_broadcast)]
    },
    fallbacks=[CommandHandler("cancel", cancel_bc), MessageHandler(filters.Regex("^❌ Cancel$"), cancel_bc)]
)

async def handle_bc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "bc_dashboard_return":
        await query.message.delete()
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
