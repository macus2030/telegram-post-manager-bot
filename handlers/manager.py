from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters
from telegram.constants import ParseMode
from storage import get_all_posts, get_post, update_post, delete_post, clone_post, restore_post
from utils.helpers import check_admin, send_temp_message, show_loading
import asyncio

# Pagination size
# Pagination size
PAGE_SIZE = 5

# Edit States
EDIT_CHOICE, EDIT_INPUT = range(2)

async def post_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    await show_post_list(update, context, page=0, category_filter="All")

async def show_post_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, category_filter: str):
    posts = get_all_posts()
    
    # Filter
    filtered_posts = []
    for pid, p in posts.items():
        if category_filter == "All" or p.get("category") == category_filter:
            if p.get("status") != "deleted": # Don't show deleted default
                filtered_posts.append((int(pid), p))
    
    # Sort by ID desc
    filtered_posts.sort(key=lambda x: x[0], reverse=True)
    
    total_posts = len(filtered_posts)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    current_page_posts = filtered_posts[start:end]
    
    text = f"📝 *Post Manager* (Filter: {category_filter})\n\n"
    
    kb = []
    for pid, p in current_page_posts:
        icon = "📂" if p.get("type") == "file" else "🔗"
        status = "🔴" if p.get("status") == "disabled" else "🟢"
        if p.get("status") == "draft": status = "📝"
            
        btn_text = f"{status} #{pid} {icon} {p.get('category')} | 👁 {p.get('views')}"
        kb.append([InlineKeyboardButton(btn_text, callback_data=f"view_{pid}")])
    
    # Pagination & Filter Controls
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅ Prev", callback_data=f"list_{category_filter}_{page-1}"))
    if end < total_posts:
        nav_row.append(InlineKeyboardButton("Next ➡", callback_data=f"list_{category_filter}_{page+1}"))
    if nav_row: kb.append(nav_row)
    
    # Filter Row
    filter_row = [
        InlineKeyboardButton("All", callback_data=f"list_All_0"),
        InlineKeyboardButton("😂", callback_data=f"list_Comedy_0"),
        InlineKeyboardButton("🔥", callback_data=f"list_Action_0"),
        InlineKeyboardButton("😱", callback_data=f"list_Horror_0")
    ]
    kb.append(filter_row)
    
    # Dashboard back
    # kb.append([InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard_main")]) # Done via ReplyKB usually
    
    markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

async def view_post_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    post_id = query.data.split("_")[1]
    await render_post_detail(update, context, post_id)

async def render_post_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: str):
    post = get_post(post_id)
    
    if not post:
        text = "❌ Post not found."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    text = (
        f"📄 *Post Details #{post_id}*\n\n"
        f"**Type**: {post.get('type', 'link')}\n"
        f"**Status**: {post.get('status')}\n"
        f"**Category**: {post.get('category')}\n"
        f"**Views**: {post.get('views')}\n"
        f"**Link**: {post.get('link', 'N/A')}\n"
        f"**File**: {post.get('file_name', 'N/A')}\n\n"
        f"**Caption**:\n_{post.get('caption')}_"
    )
    
    kb = [
        [InlineKeyboardButton("📋 Copy Deep Link", callback_data=f"copy_{post_id}")],
        [InlineKeyboardButton("✏ Edit", callback_data=f"editopt_{post_id}"), InlineKeyboardButton("🧬 Clone", callback_data=f"clone_{post_id}")],
        [InlineKeyboardButton("🔴 Disable" if post.get("status") == "active" else "🟢 Enable", callback_data=f"toggle_{post_id}"), InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{post_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="list_All_0")]
    ]
    
    # Add Preview Button
    kb.insert(1, [InlineKeyboardButton("👁 Preview Content", callback_data=f"preview_{post_id}")])
    
    markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        # If triggered from message handler (after edit)
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

# --- EDIT POST CONVERSATION ---

async def start_edit_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    post_id = query.data.split("_")[1]
    context.user_data['edit_pid'] = post_id
    
    kb = [
        [InlineKeyboardButton("📝 Edit Caption", callback_data="field_caption")],
        [InlineKeyboardButton("🏷 Edit Category", callback_data="field_category")],
        [InlineKeyboardButton("🔗 Edit Link", callback_data="field_link")],
        [InlineKeyboardButton("🔙 Cancel", callback_data="cancel_edit")]
    ]
    
    await query.edit_message_text(
        f"✏ *Editing Post #{post_id}*\n\nSelect what you want to edit:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN
    )
    return EDIT_CHOICE

async def edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "cancel_edit":
        # Return to details
        pid = context.user_data.get('edit_pid')
        await render_post_detail(update, context, pid)
        return ConversationHandler.END
    
    field_map = {
        "field_caption": "caption",
        "field_category": "category",
        "field_link": "link"
    }
    
    field = field_map.get(data)
    if not field:
        return EDIT_CHOICE
        
    context.user_data['edit_field'] = field
    
    # Specific prompt based on field
    prompt = "Enter the new value:"
    if field == "caption":
        prompt = "📝 Send the new *Caption* for this post:"
    elif field == "category":
        prompt = "🏷 Send the new *Category* name (e.g. Comedy, Action):"
    elif field == "link":
        prompt = "🔗 Send the new *Link* URL:"
        
    kb = [[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_edit")]]
    
    await query.edit_message_text(
        prompt,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN
    )
    return EDIT_INPUT

async def edit_input_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    pid = context.user_data.get('edit_pid')
    field = context.user_data.get('edit_field')
    
    if not pid or not field:
        await update.message.reply_text("❌ Error: Session expired.")
        return ConversationHandler.END
        
    # Update DB
    update_post(pid, {field: text})
    
    await update.message.reply_text(f"✅ *{field.capitalize()} updated!*", parse_mode=ParseMode.MARKDOWN)
    
    # Show details again
    await render_post_detail(update, context, pid)
    return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    
    pid = context.user_data.get('edit_pid')
    if pid:
        # If we can edit the message (from button cancellation)
         if query:
             await render_post_detail(update, context, pid)
         else:
             # From command cancellation
             await update.message.reply_text("❌ Edit Cancelled.")
             await render_post_detail(update, context, pid)
    else:
        await update.message.reply_text("❌ Edit Cancelled.")
        
    return ConversationHandler.END

edit_post_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_post, pattern="^editopt_")],
    states={
        EDIT_CHOICE: [CallbackQueryHandler(edit_choice, pattern="^(field_|cancel_edit)")],
        EDIT_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_input_value),
            CallbackQueryHandler(edit_choice, pattern="^cancel_edit$")
        ]
    },
    fallbacks=[
        CommandHandler("cancel", cancel_edit),
        CallbackQueryHandler(cancel_edit, pattern="^cancel_edit$")
    ]
)

async def handle_manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("list_"):
        _, cat, page = data.split("_")
        await show_post_list(update, context, int(page), cat)
        
    elif data.startswith("view_"):
        await view_post_detail(update, context)
        
    elif data.startswith("toggle_"):
        pid = data.split("_")[1]
        p = get_post(pid)
        new_status = "disabled" if p.get("status") == "active" else "active"
        update_post(pid, {"status": new_status})
        await view_post_detail(update, context) # Refresh
        
    elif data.startswith("delete_"):
        pid = data.split("_")[1]
        delete_post(pid) # Soft delete
        
        kb = [[InlineKeyboardButton("↩ Undo", callback_data=f"undo_{pid}")]]
        await query.edit_message_text(f"🗑 Post #{pid} deleted.", reply_markup=InlineKeyboardMarkup(kb))
        
        # Schedule cleanup
        context.application.create_task(cleanup_undo_button(update, context, pid))

    elif data.startswith("undo_"):
        pid = data.split("_")[1]
        restore_post(pid)
        await query.answer("✅ Restored!")
        # Go back to details
        await render_post_detail(update, context, pid)
        
    elif data.startswith("clone_"):
        pid = data.split("_")[1]
        new_id = clone_post(pid)
        await query.answer(f"✅ Cloned to #{new_id}")
        # Go to new post
        query.data = f"view_{new_id}"
        await view_post_detail(update, context)

    elif data.startswith("preview_"):
        pid = data.split("_")[1]
        post = get_post(pid)
        # Send actual content temp
        await query.answer("Sent preview below 👇")
        # Logic similar to user handler but for admin
        caption = f"[PREVIEW] {post.get('caption')}"
        if post.get('type') == 'file':
            await context.bot.send_document(chat_id=update.effective_chat.id, document=post.get('file_id'), caption=caption)
        else:
             await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{caption}\n{post.get('link')}")

    elif data.startswith("copy_"):
        pid = data.split("_")[1]
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={pid}"
        await query.answer(link, show_alert=True) # Mobile users can copy from alert? Or just send text.
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"`{link}`", parse_mode=ParseMode.MARKDOWN)

async def cleanup_undo_button(update: Update, context: ContextTypes.DEFAULT_TYPE, pid: str):
    await asyncio.sleep(10)
    try:
        p = get_post(pid)
        # If still deleted, remove the undo button
        if p and p.get("status") == "deleted":
             await update.callback_query.edit_message_text(f"🗑 Post #{pid} deleted permanently.")
    except Exception:
        pass

