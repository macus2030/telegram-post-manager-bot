from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from storage import get_all_posts
from utils.helpers import check_admin

async def stats_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    posts = get_all_posts()
    total_posts = len(posts)
    total_views = sum(p.get('views', 0) for p in posts.values())
    active_posts = sum(1 for p in posts.values() if p.get('status') == 'active')
    
    # Calculate Category Stats
    cat_counts = {}
    for p in posts.values():
        c = p.get('category', 'Uncategorized')
        cat_counts[c] = cat_counts.get(c, 0) + 1
        
    sorted_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cats_str = "\n".join([f"- {c}: {n} posts" for c, n in sorted_cats])
    
    # Top Posts
    sorted_posts = sorted(posts.items(), key=lambda x: x[1].get('views', 0), reverse=True)[:5]
    top_posts_str = ""
    for pid, p in sorted_posts:
        top_posts_str += f"- #{pid} ({p.get('category')}): **{p.get('views')}** views\n"
    
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
