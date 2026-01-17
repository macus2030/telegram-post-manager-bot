from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from storage import get_post_stats
from utils.helpers import check_admin

async def stats_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    stats = get_post_stats()
    
    total_posts = stats["total_posts"]
    total_views = stats["total_views"]
    active_posts = stats["active_posts"]
    
    top_cats_str = "\n".join([f"- {c}: {n} posts" for c, n in stats["top_categories"]])
    
    top_posts_str = ""
    for p in stats["top_posts"]:
        top_posts_str += f"- #{p['id']} ({p['category']}): **{p['views']}** views\n"
    
    text = (
        "📊 *Statistics Dashboard*\n\n"
        f"**Totals**:\n"
        f"✅ Active Posts: `{active_posts}`\n"
        f"📝 Total Posts: `{total_posts}`\n"
        f"👁 Total Views: `{total_views}`\n\n"
        f"**Top Categories**:\n{top_cats_str}\n\n"
        f"**Top Performing Posts**:\n{top_posts_str}"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
