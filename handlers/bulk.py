from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from telegram.constants import ParseMode
from storage import add_post
from utils.helpers import check_admin, send_temp_message

# States
INPUT_LINKS, SELECT_CATEGORY_BULK = range(2)

async def start_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    await update.message.reply_text(
        "📦 *Bulk Create Posts*\n\n"
        "Send me a list of links (one per line).\n"
        "I will create a post for each one using the default template.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    return INPUT_LINKS

async def handle_bulk_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    links = [l.strip() for l in text.split('\n') if l.strip().startswith('http')]
    
    if not links:
        await update.message.reply_text("⚠ No valid links found. Please try again (start with http/https).")
        return INPUT_LINKS
        
    context.user_data['bulk_links'] = links
    
    # Select Category
    categories = ["😂 Comedy", "😱 Horror", "🔥 Action", "❤️ Romance", "❌ Skip"]
    kb = [categories]
    
    await update.message.reply_text(
        f"✅ Found {len(links)} links.\n"
        "Now select a category for ALL these posts:",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN
    )
    return SELECT_CATEGORY_BULK

async def handle_bulk_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = update.message.text
    if cat == "❌ Skip": cat = "Uncategorized"
    else: cat = cat.split(" ")[-1] # Remove emoji
    
    links = context.user_data.get('bulk_links', [])
    created_posts = []
    
    for link in links:
        pid = add_post({
            "type": "link",
            "link": link,
            "caption": f"Check this out!\n{link}",
            "category": cat,
            "status": "active",
            "views": 0,
            "tags": [],
            "note": "Bulk created"
        })
        created_posts.append(pid)
        
    bot_username = context.bot.username
    summary = f"✅ *Success! Created {len(created_posts)} posts* (Category: {cat})\n\n"
    
    for pid in created_posts:
        link = f"https://t.me/{bot_username}?start={pid}"
        summary += f"#{pid} -> `{link}`\n"
        
    await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN)
    
    # Back to dashboard
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

async def cancel_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Bulk creation cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

bulk_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^📦 Bulk Create$"), start_bulk)],
    states={
        INPUT_LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_links)],
        SELECT_CATEGORY_BULK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bulk_category)]
    },
    fallbacks=[CommandHandler("cancel", cancel_bulk)]
)
