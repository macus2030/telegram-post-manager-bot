from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, error
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, ConversationHandler, MessageHandler, filters
from telegram.constants import ParseMode
from storage import get_posts_paginated, get_posts_count, get_post, update_post, delete_post, clone_post, restore_post
from utils.helpers import check_admin, send_temp_message, show_loading
from handlers.admin import MENU_REGEX, global_fallback, cancel
import asyncio
import logging

# Pagination size
# Pagination size
PAGE_SIZE = 5

# Edit States
EDIT_CHOICE, EDIT_INPUT, EDIT_CATEGORY_SELECT = range(3)

async def post_manager(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not check_admin(update.effective_user.id): return
    
    await show_post_list(update, context, page=0, category_filter="All")

async def show_post_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, category_filter: str):
    # Optimized Pagination
    total_posts = get_posts_count(category_filter)
    current_page_posts = get_posts_paginated(page, PAGE_SIZE, category_filter)
    
    start = page * PAGE_SIZE
    end = start + len(current_page_posts)
    
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
    from storage import get_categories
    categories = get_categories()
    filter_row = [InlineKeyboardButton("All", callback_data=f"list_All_0")]
    
    # Add first 3 categories
    for i, (cid, cat) in enumerate(categories.items()):
        if i >= 3: break
        filter_row.append(InlineKeyboardButton(cat['name'][:10], callback_data=f"list_{cat['name']}_0"))
        
    kb.append(filter_row)
    
    # Delete All Button (Only on main view)
    if page == 0 and category_filter == "All":
         kb.append([InlineKeyboardButton("🗑 Delete ALL Posts", callback_data="delall_confirm")])

    # Dashboard back
    kb.append([InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard_return")])
    
    markup = InlineKeyboardMarkup(kb)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except error.BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise e # Re-raise if other error
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
        f"**File**: {post.get('file_name', 'N/A')}\n"
    )
    
    if post.get('password'):
        text += f"**Password**: `{post.get('password')}`\n"
        
    text += (
        f"**Timer**: {post.get('auto_delete_timer', 'Default')} mins\n\n"
        f"**Caption**:\n_{post.get('caption')}_"
    )
    
    kb = [
        [InlineKeyboardButton("📋 Copy Link", callback_data=f"copy_{post_id}")],
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
    
    post = get_post(post_id)
    
    kb = [
        [InlineKeyboardButton("📝 Edit Caption", callback_data="field_caption")],
        [InlineKeyboardButton("🏷 Edit Category", callback_data="field_category")],
        [InlineKeyboardButton("🔗 Edit Link", callback_data="field_link")],
        [InlineKeyboardButton("⏱️ Edit Timer", callback_data="field_timer")]
    ]
    
    if post and post.get('type') == 'file':
        kb.insert(1, [InlineKeyboardButton("📂 Reupload File", callback_data="field_file")])
        kb.insert(2, [InlineKeyboardButton("🔑 Edit Password", callback_data="field_password")])
        
    kb.append([InlineKeyboardButton("🔙 Cancel", callback_data="cancel_edit")])
    
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
        "field_link": "link",
        "field_timer": "auto_delete_timer",
        "field_file": "file",
        "field_password": "password"
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
        # Multi-Select Logic for Edit
        # Parse current categories
        pid = context.user_data.get('edit_pid')
        post = get_post(pid)
        current_cats_str = post.get('category', 'Uncategorized')
        
        # Split by likely separators (double space, pipe, comma)
        import re
        # Split by "  " or " | " or ","
        parts = re.split(r"  | \| |,", current_cats_str)
        selected = [p.strip() for p in parts if p.strip()]
        
        context.user_data['edit_selected_categories'] = selected
        
        return await show_edit_category_selector(update, context)
        
    elif field == "link":
        prompt = "🔗 Send the new *Link* URL:"
    elif field == "auto_delete_timer":
        prompt = "⏱️ Send new **Auto-Delete Timer** in minutes (e.g. `10`, `60`).\nSend `0` to use Global Default."
    elif field == "file":
        prompt = "📂 Send the **New File** (Document, Video, or Audio) to replace the existing one:"
    elif field == "password":
        prompt = "🔑 Send the **New Password** for this file post:"
        
    kb = [[InlineKeyboardButton("🔙 Cancel", callback_data="cancel_edit")]]
    
    await query.edit_message_text(
        prompt,
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN
    )
    return EDIT_INPUT

async def edit_input_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pid = context.user_data.get('edit_pid')
    field = context.user_data.get('edit_field')
    
    if not pid or not field:
        await update.message.reply_text("❌ Error: Session expired.")
        return ConversationHandler.END

    updates = {}
    
    # Handle File Upload
    if field == "file":
        doc = update.message.effective_attachment
        if isinstance(doc, list): doc = doc[-1] # Photo gives list
        
        if not doc:
            await update.message.reply_text("❌ Please send a valid file/video/audio.")
            return EDIT_INPUT
            
        # Get attributes
        file_id = doc.file_id
        file_unique_id = doc.file_unique_id
        file_name = getattr(doc, 'file_name', f"file_{pid}")
        mime_type = getattr(doc, 'mime_type', 'application/octet-stream')
        file_size = getattr(doc, 'file_size', 0)
        
        updates = {
            "file_id": file_id,
            "file_unique_id": file_unique_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_size": file_size
        }
        
    else:
        # Handle Text Inputs
        text = update.message.text
        if not text:
             await update.message.reply_text("❌ text expected.")
             return EDIT_INPUT
             
        updates = {field: text}

        # Validation/Formatting for specific fields
        if field == "link":
            text = text.strip()
            if not (text.startswith("http://") or text.startswith("https://")):
                text = f"https://{text}"
            updates[field] = text
        
        elif field == "auto_delete_timer":
            if not text.isdigit():
                 await update.message.reply_text("❌ Invalid input. Please enter a number (minutes).")
                 return EDIT_INPUT
            updates[field] = text
                 
        elif field == "password":
            # Sync with caption
            current_post = get_post(pid)
            current_caption = current_post.get("caption", "")
            import re
            # Replace existing password line or append
            if "Password:" in current_caption:
                new_caption = re.sub(r"(Password:\s*)(.*)", f"\\g<1>{text}", current_caption)
                updates["caption"] = new_caption
            else:
                # If not found, maybe append it?
                pass
            
            # Explicitly set password field
            updates["password"] = text

    # Update DB
    update_post(pid, updates)
    
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

async def show_edit_category_selector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected = context.user_data.get('edit_selected_categories', [])
    
    from storage import get_categories
    categories_data = get_categories()
    categories = [c['name'] for c in categories_data.values()]
    if not categories:
        categories = ["Uncategorized"]
    
    # Build Keyboard (ReplyKeyboardMarkup like Admin)
    # But wait, Manager uses InlineKeyboard?
    # NO, Manager flow `edit_input_value` uses MessageHandler filters.TEXT.
    # So we can use ReplyKeyboard for the selection phase if we want consistency with Admin.
    # BUT Manager is triggered by Inline Buttons. 
    # Mixing Inline and Reply is okay.
    
    # Let's use ReplyKeyboard for selection to match Admin's style which is robust.
    
    kb = []
    row = []
    for cat in categories:
        label = f"✅ {cat}" if cat in selected else cat
        row.append(label)
        if len(row) == 2:
            kb.append(row)
            row = []
    if row: kb.append(row)
    
    kb.append(["✅ Done", "❌ Clear"])
    kb.append(["🏠 Dashboard"])
    
    text = (
        f"🏷 *Edit Categories*\n\n"
        f"Selected: *{'  '.join(selected) if selected else '(None)'}*\n\n"
        "Click to toggle. Press **Done** when finished."
    )
    
    # If called from CallbackQuery (initially)
    if update.callback_query:
        # We cannot send ReplyMarkup in edit_message_text easily (it shows in chat input).
        # We must send a NEW message with ReplyMarkup.
        # And delete the old Inline one? Or just leave it?
        await update.callback_query.delete_message()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        # Called from MessageHandler (toggle loop)
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )
    return EDIT_CATEGORY_SELECT

async def handle_edit_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    # Done Logic
    if text == "✅ Done":
        selected = context.user_data.get('edit_selected_categories', [])
        pid = context.user_data.get('edit_pid')
        
        if not selected:
             await update.message.reply_text("⚠ Select at least one category.")
             return EDIT_CATEGORY_SELECT
             
        final_str = "  ".join(selected)
        update_post(pid, {"category": final_str})
        
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(f"✅ Categories updated: `{final_str}`", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN)
        
        # Show details again
        await render_post_detail(update, context, pid)
        return ConversationHandler.END
        
    # Clear Logic
    if text == "❌ Clear":
        context.user_data['edit_selected_categories'] = []
        return await show_edit_category_selector(update, context)
        
    # Toggle Logic
    from storage import get_categories
    valid_names = [c['name'] for c in get_categories().values()]
    
    cat = text.replace("✅ ", "")
    if cat not in valid_names:
         # Check if user clicked a menu button? handled by fallback?
         # Check global fallback regex manually if missed?
         pass
         
    selected = context.user_data.get('edit_selected_categories', [])
    if cat in selected:
        selected.remove(cat)
    else:
        selected.append(cat)
        
    context.user_data['edit_selected_categories'] = selected
    return await show_edit_category_selector(update, context)

edit_post_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_post, pattern="^editopt_")],
    states={
        EDIT_CHOICE: [CallbackQueryHandler(edit_choice, pattern="^(field_|cancel_edit)")],
        EDIT_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), edit_input_value),
            MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.PHOTO, edit_input_value),
            CallbackQueryHandler(edit_choice, pattern="^cancel_edit$")
        ],
        EDIT_CATEGORY_SELECT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), handle_edit_category_selection)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel_edit),
        CallbackQueryHandler(cancel_edit, pattern="^cancel_edit$")
    ],
    per_message=False # Suppress warning, as we track per user
)

async def handle_manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # helper to ensure we answer
    async def try_answer(text=None, alert=False):
        try:
            await query.answer(text=text, show_alert=alert)
        except:
             pass

    try:
        if data.startswith("list_"):
            # We should answer to stop spinner
            await try_answer()
            _, cat, page = data.split("_")
            await show_post_list(update, context, int(page), cat)
            
        elif data.startswith("view_"):
            # view_post_detail answers itself, but safe to answer here too if we want?
            # view_post_detail calls answer(). Let's leave it.
            await view_post_detail(update, context)
            
        elif data.startswith("toggle_"):
            # logic updates db then calls view_post_detail
            # view_post_detail calls answer.
            pid = data.split("_")[1]
            p = get_post(pid)
            if p:
                new_status = "disabled" if p.get("status") == "active" else "active"
                update_post(pid, {"status": new_status})
            await view_post_detail(update, context)
            
        elif data.startswith("delete_"):
            await try_answer("Deleting...")
            pid = data.split("_")[1]
            delete_post(pid) # Soft delete
            
            kb = [[InlineKeyboardButton("↩ Undo", callback_data=f"undo_{pid}")]]
            try:
                await query.edit_message_text(f"🗑 Post #{pid} deleted.", reply_markup=InlineKeyboardMarkup(kb))
            except Exception:
                await try_answer("Could not edit message", alert=True)
            
            # Schedule cleanup
            context.application.create_task(cleanup_undo_button(update, context, pid))

        elif data.startswith("undo_"):
            pid = data.split("_")[1]
            restore_post(pid)
            await try_answer("✅ Restored!")
            # Go back to details
            await render_post_detail(update, context, pid)
            
        elif data.startswith("clone_"):
            pid = data.split("_")[1]
            new_id = clone_post(pid)
            await try_answer(f"✅ Cloned to #{new_id}")
            # Go to new post
            # modify query.data so view_post_detail sees new id?
            # view_post_detail reads query.data.split("_")[1]
            # We can't easily modify read-only object properties usually.
            # Call render_post_detail directly? Yes.
            await render_post_detail(update, context, str(new_id))

        elif data.startswith("preview_"):
            pid = data.split("_")[1]
            post = get_post(pid)
            if not post:
                await try_answer("Post not found", alert=True)
                return

            await try_answer("Sent preview below 👇")
            
            caption = f"[PREVIEW] {post.get('caption')}"
            try:
                if post.get('type') == 'file':
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=post.get('file_id'), caption=caption)
                else:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"{caption}\n{post.get('link')}")
            except Exception as e:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Preview failed: {e}")

        elif data.startswith("delall_"):
             if data == "delall_confirm":
                 await confirm_delete_all(update, context)
             elif data == "delall_schedule":
                 await schedule_delete_all(update, context)
             elif data.startswith("delall_undo_"):
                 await undo_delete_all(update, context)

        elif data.startswith("copy_"):
            pid = data.split("_")[1]
            from utils.helpers import encode_payload
            enc_id = encode_payload(pid)
            bot_username = context.bot.username
            link = f"https://t.me/{bot_username}?start={enc_id}"
            await try_answer(link, alert=True) 
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"`{link}`", parse_mode=ParseMode.MARKDOWN)

        elif data == "dashboard_return":
            # admin_dashboard handles answer now?
            # handlers/admin.py admin_dashboard checks if update.callback_query and answers.
            from handlers.admin import admin_dashboard
            await admin_dashboard(update, context)
            return ConversationHandler.END
            
    except Exception as e:
        import traceback
        logging.error(f"Manager Callback Error: {e}", exc_info=True)
        await try_answer(f"❌ Error: {e}", alert=True)


async def cleanup_undo_button(update: Update, context: ContextTypes.DEFAULT_TYPE, pid: str):
    await asyncio.sleep(10)
    try:
        p = get_post(pid)
        # If still deleted, remove the undo button
        if p and p.get("status") == "deleted":
             await update.callback_query.edit_message_text(f"🗑 Post #{pid} deleted permanently.")
    except Exception:
        pass

async def confirm_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    await query.message.reply_text(
        "⚠ **WARNING: DATA LOSS** ⚠\n\n"
        "Are you sure you want to delete **ALL POSTS**?\n"
        "This action cannot be undone (after the safety timer).",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧨 Yes, Delete Everything", callback_data="delall_schedule")],
            [InlineKeyboardButton("🔙 Cancel", callback_data="dashboard")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def schedule_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Schedule Job
    job_name = f"delall_{query.from_user.id}"
    context.job_queue.run_once(execute_delete_all_job, 10, name=job_name, chat_id=query.message.chat_id)
    
    await query.message.reply_text(
        "🚨 **DELETION INITIATED** 🚨\n\n"
        "All posts will be deleted in **10 seconds**.\n"
        "Click UNDO to cancel!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ UNDO DELETION", callback_data=f"delall_undo_{job_name}")]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )

async def undo_delete_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data 
    job_name = data.replace("delall_undo_", "")
    
    jobs = context.job_queue.get_jobs_by_name(job_name)
    if jobs:
        for job in jobs:
            job.schedule_removal()
        await query.answer("Deletion Cancelled!")
        await query.message.reply_text("✅ **Restored!** No posts were deleted.")
    else:
        await query.answer("Too late!", show_alert=True)
        await query.message.reply_text("❌ **Too late.** The deletion has already executed.")
        
    # Return to manager
    await show_post_list(update, context, 0, "All")

async def execute_delete_all_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    from storage import delete_all_posts
    
    success = delete_all_posts()
    
    if success:
        await context.bot.send_message(job.chat_id, "🗑 **System Purge Complete**.\nAll posts have been deleted.")
    else:
        await context.bot.send_message(job.chat_id, "❌ Error occurred during deletion.")
