from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode
from storage import search_posts_advanced
from utils.helpers import check_admin
from handlers.admin import MENU_REGEX, global_fallback

# States
SEARCH_CHOICE, SEARCH_FILTER_TYPE, SEARCH_FILTER_STATUS, SEARCH_INPUT = range(4)

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    # Reset filters
    context.user_data['search_type'] = None
    context.user_data['search_status'] = None
    
    # Ask mode
    await update.message.reply_text(
        "🔍 *Search Mode*\n\n"
        "Choose your search method:",
        reply_markup=ReplyKeyboardMarkup([["🔎 Simple Search", "⚙️ Advanced Filter"], ["🏠 Dashboard"]], resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return SEARCH_CHOICE

async def handle_search_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🏠 Dashboard":
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    if text == "🔎 Simple Search":
        await update.message.reply_text("🔎 Enter keywords or Post ID:", reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True))
        return SEARCH_INPUT
        
    if text == "⚙️ Advanced Filter":
        await update.message.reply_text(
            "⚙️ *Filter by Type*\n\nSelect post type:",
            reply_markup=ReplyKeyboardMarkup([["All", "File", "Link"], ["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return SEARCH_FILTER_TYPE
        
    return SEARCH_CHOICE

async def handle_filter_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await cancel_search(update, context)
        
    if text in ["All", "File", "Link"]:
        context.user_data['search_type'] = text
        
        await update.message.reply_text(
            "⚙️ *Filter by Status*\n\nSelect post status:",
            reply_markup=ReplyKeyboardMarkup([["All", "Active", "Disabled"], ["❌ Cancel"]], resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
        return SEARCH_FILTER_STATUS
        
    await update.message.reply_text("⚠ Invalid selection.")
    return SEARCH_FILTER_TYPE

async def handle_filter_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await cancel_search(update, context)
        
    if text in ["All", "Active", "Disabled"]:
        context.user_data['search_status'] = text
        
        await update.message.reply_text(
            "🔎 *Enter Search Query*\n\n"
            "Keywords or ID:",
             reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
             parse_mode=ParseMode.MARKDOWN
        )
        return SEARCH_INPUT
        
    await update.message.reply_text("⚠ Invalid selection.")
    return SEARCH_FILTER_STATUS

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    
    if query == "❌ Cancel":
        return await cancel_search(update, context)
    
    type_filter = context.user_data.get('search_type')
    status_filter = context.user_data.get('search_status')
    
    # Run Search
    results = search_posts_advanced(query, type_filter, status_filter, limit=20)
    
    if not results:
        await update.message.reply_text("❌ No results found. Try again.")
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
    
    # Show results
    import html
    summary = f"🔍 Found {len(results)} matches"
    if type_filter: summary += f" (Type: {type_filter})"
    if status_filter: summary += f" (Status: {status_filter})"
    summary += ":\n\n"
    
    for pid, p in results[:10]:
        icon = "📂" if p.get("type") == "file" else "🔗"
        st = "active" if p.get("status")=="active" else "🔴"
        safe_caption = html.escape(p.get('caption', '')[:30])
        summary += f"#{pid} {st} {icon} {safe_caption}...\n"
        
    await update.message.reply_text(summary, parse_mode=ParseMode.HTML)
    
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Search cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

search_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^🔍 Search$"), start_search)],
    states={
        SEARCH_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_choice)],
        SEARCH_FILTER_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filter_type)],
        SEARCH_FILTER_STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_filter_status)],
        SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search)]
    },
    fallbacks=[CommandHandler("cancel", cancel_search), MessageHandler(filters.Regex(MENU_REGEX), global_fallback)]
)
