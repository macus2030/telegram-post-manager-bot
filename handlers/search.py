from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from storage import get_all_posts, get_post
from utils.helpers import check_admin

# States
SEARCH_INPUT = range(1)

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    await update.message.reply_text(
        "🔍 *Search Posts*\n\n"
        "Enter a Post ID (e.g. `12`) OR keywords to search in captions/links.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return SEARCH_INPUT

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.lower().strip()
    posts = get_all_posts()
    
    results = []
    
    # 1. Direct ID match
    if query.isdigit() and query in posts:
        results.append((query, posts[query]))
    
    # 2. Search Text
    else:
        for pid, p in posts.items():
            content = (p.get('caption', '') + p.get('link', '') + p.get('file_name', '')).lower()
            if query in content:
                results.append((pid, p))
                
    if not results:
        await update.message.reply_text("❌ No results found. Try again.")
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context) # Or stay in search loop? Better exit to avoid trap
        return ConversationHandler.END
    
    # Show results
    summary = f"🔍 Found {len(results)} matches for '{query}':\n\n"
    for pid, p in results[:10]: # Limit to 10
        icon = "📂" if p.get("type") == "file" else "🔗"
        summary += f"#{pid} {icon} {p.get('caption')[:30]}...\n"
        
    await update.message.reply_text(summary)
    
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
        SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_search)]
    },
    fallbacks=[CommandHandler("cancel", cancel_search)]
)
