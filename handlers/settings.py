from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from storage import get_message_template, update_message_template, get_help_link, update_help_link, get_main_template, update_main_template, get_auto_delete_timer, update_auto_delete_timer, get_protect_content, update_protect_content, get_welcome_message, update_welcome_message
from utils.helpers import check_admin
from config import HOW_TO_OPEN_LINK
from handlers.admin import MENU_REGEX, global_fallback, cancel
import logging

# States
SELECT_SETTING, EDIT_MSG_TEMPLATE, EDIT_HELP_LINK, EDIT_MAIN_TEMPLATE, MANAGE_FORCE_SUB, ADD_FS_CHANNEL, EDIT_GLOBAL_TIMER, EDIT_WELCOME_MSG = range(8)

async def settings_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for Settings."""
    if not check_admin(update.effective_user.id): return ConversationHandler.END
    
    return await show_settings_menu(update, context)

async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚙️ *Settings Menu*\n\n"
        "Select what you want to configure:"
    )
    
    kb = [
        ["📝 Edit Message Template", "📢 Edit Main Channel Template"],
        ["🔗 Edit Help Link", "🔐 Manage Force Subscribe"],
        ["⏱️ Edit Global Timer", "🔒 Toggle Content Protection"],
        ["👋 Edit Welcome Message"],
        ["🔙 Back to Dashboard"]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return SELECT_SETTING

async def handle_setting_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Back to Dashboard":
        from handlers.admin import admin_dashboard
        await admin_dashboard(update, context)
        return ConversationHandler.END
        
    if text == "📝 Edit Message Template":
        current_template = get_message_template()
        await update.message.reply_text(
            "📝 *Edit Message Template*\n\n"
            "Current Template:\n"
            f"```\n{current_template}\n```\n\n"
            "**Available Variables:**\n"
            "• `{post_id}` : Post Number\n"
            "• `{caption}` : Post Caption\n"
            "• `{link}` : Original Link\n"
            "• `{short_link}` : Shortened Link\n"
            "• `{how_to_open_link}` : Help Link\n"
            "• `{time}` : Auto-Delete Time (mins)\n\n"
            "Send the new template structure now:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_MSG_TEMPLATE
        
    if text == "🔗 Edit Help Link":
         current_link = get_help_link()
         await update.message.reply_text(
            "🔗 *Edit Help Link*\n\n"
            f"Current Link: `{current_link}`\n\n"
            "Send the new URL for the 'How to Open' link:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
             parse_mode="Markdown"
        )
         return EDIT_HELP_LINK
         
    if text == "📢 Edit Main Channel Template":
        current = get_main_template()
        await update.message.reply_text(
            "📢 *Edit Main Channel Template*\n\n"
            "Current Template:\n"
            f"```\n{current}\n```\n\n"
            "Send the new template structure now:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_MAIN_TEMPLATE

    if text == "🔐 Manage Force Subscribe":
        return await manage_force_sub(update, context)

    if text == "⏱️ Edit Global Timer":
        current_seconds = get_auto_delete_timer()
        current_mins = int(current_seconds / 60)
        await update.message.reply_text(
            "⏱️ *Edit Global Auto-Delete Timer*\n\n"
            f"Current Timer: **{current_mins} minutes**\n\n"
            "This timer applies to all posts unless they have a custom timer set.\n"
            "Send the new time in **minutes** (e.g. `30`, `60`).",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_GLOBAL_TIMER

    if text == "🔒 Toggle Content Protection":
        return await toggle_content_protection(update, context)

    if text == "👋 Edit Welcome Message":
        current = get_welcome_message()
        await update.message.reply_text(
            "👋 *Edit Welcome Message*\n\n"
            "This is the message users see when they start the bot without a link.\n\n"
            f"**Current**:\n`{current}`\n\n"
            "Send the new message:",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel", "🏠 Dashboard"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return EDIT_WELCOME_MSG

    await update.message.reply_text("Invalid selection.")
    return SELECT_SETTING

async def save_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    update_welcome_message(text)
    await update.message.reply_text("✅ Welcome Message updated!", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def toggle_content_protection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = get_protect_content()
    new_state = not current
    update_protect_content(new_state)
    
    status = "✅ ON" if new_state else "❌ OFF"
    await update.message.reply_text(
        f"🔒 **Content Protection Updated**\n\n"
        f"Status: **{status}**\n"
        "When ON, users cannot forward or save files from the bot.",
        parse_mode="Markdown"
    )
    return await show_settings_menu(update, context)

async def manage_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from storage import get_force_subs
    # We use InlineButtons for removing, Reply for Adding/Back
    
    channels = get_force_subs()
    
    text = "🔐 *Force Subscribe Channels*\n\nUsers MUST join these channels to use the bot.\n\n"
    if not channels:
        text += "No channels configured."
    
    kb = []
    for ch in channels:
        text += f"• {ch['title']} (ID: `{ch['id']}`)\n"
        kb.append([InlineKeyboardButton(f"🗑 Remove {ch['title']}", callback_data=f"fs_rem_{ch['id']}")])
        
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb) if kb else None,
        parse_mode="Markdown"
    )
    
    await update.message.reply_text(
        "Select an action:",
        reply_markup=ReplyKeyboardMarkup([["➕ Add Channel"], ["🔙 Back"]], resize_keyboard=True)
    )
    return MANAGE_FORCE_SUB

async def handle_fs_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == "🔙 Back":
        return await show_settings_menu(update, context)
        
    if text == "➕ Add Channel":
        await update.message.reply_text(
            "➕ *Add Force Subscribe Channel*\n\n"
            "Please forward a message from the channel or send the Channel ID (e.g. -100xxx).\n"
            "**Note**: I must be an Admin in that channel!",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return ADD_FS_CHANNEL
        
    return MANAGE_FORCE_SUB

async def add_fs_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Entered add_fs_channel with: {update.message.text}")
    try:
        msg = update.message
        if msg.text == "❌ Cancel":
             return await manage_force_sub(update, context)
             
        chat_id = None
        title = "Unknown Channel"
        invite_link = None
        
        # PTB v20+ Forward Handling
        if msg.forward_origin:
            if isinstance(msg.forward_origin, MessageOriginChannel):
                chat_id = msg.forward_origin.chat.id
                title = msg.forward_origin.chat.title
                
        # Legacy check just in case (or if user is using older version? requirements says >=20)
        elif hasattr(msg, 'forward_from_chat') and msg.forward_from_chat:
            chat_id = msg.forward_from_chat.id
            title = msg.forward_from_chat.title
            
        elif msg.text: # Logic if NOT forwarded or forward extraction failed
            text = msg.text.strip()
            if text.startswith("-100") or text.lstrip("-").isdigit():
                 chat_id = int(text)
            else:
                 chat_id = text
                 
        if not chat_id:
             # If we have text but it wasn't an ID, and it wasn't a channel forward,
             # it might be a username or invalid text.
             if msg.text:
                 chat_id = msg.text
             else:
                await update.message.reply_text("❌ Invalid input. Forward a message from a CHANNEL or send the ID.")
                return ADD_FS_CHANNEL
            
        status_msg = await update.message.reply_text("⏳ Verifying channel...")
        
        # Verify Bot Admin
        chat = await context.bot.get_chat(chat_id)
        
        # If we didn't get title from forward, get it from chat object
        if title == "Unknown Channel":
            title = chat.title
            
        member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if member.status != "administrator":
            await update.message.reply_text(f"❌ I am not an admin in {title}. Please promote me first.")
            return ADD_FS_CHANNEL
            
        # Get Invite Link
        invite_link = chat.invite_link
        if not invite_link:
            invite_link = await context.bot.export_chat_invite_link(chat_id)
            
        from storage import add_force_sub
        add_force_sub(chat_id, invite_link, title)
        
        await update.message.reply_text(f"✅ Added **{title}** to Force Subscribe list!", parse_mode="Markdown")
        return await manage_force_sub(update, context)
        
    except Exception as e:
        logging.error(f"Error in add_fs_channel: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Error: {e}")
        return ADD_FS_CHANNEL

async def remove_fs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    channel_id = data.split("_")[2]
    
    from storage import remove_force_sub
    remove_force_sub(channel_id)
    
    await query.answer("Channel removed!")
    
    # Refresh list
    await query.message.delete()
    return await manage_force_sub(update, context)

async def guide_fs_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text and (text.startswith("-100") or text.lstrip("-").isdigit()):
        await update.message.reply_text("⚠ Please click the **➕ Add Channel** button below first, then send the ID.")
    else:
        await update.message.reply_text("⚠ Please select an action from the menu below.")
    return MANAGE_FORCE_SUB

async def save_msg_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    update_message_template(text)
    await update.message.reply_text("✅ Message Template updated!", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def save_help_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
    
    link = text.strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        link = f"https://{link}"

    update_help_link(link)
    await update.message.reply_text(f"✅ Help Link updated to:\n`{link}`", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def save_main_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    update_main_template(text)
    await update.message.reply_text("✅ Main Channel Template updated!", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def save_global_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "❌ Cancel":
        return await show_settings_menu(update, context)
        
    if not text.isdigit():
        await update.message.reply_text("⚠ Invalid input. Please enter a number in minutes.")
        return EDIT_GLOBAL_TIMER
        
    mins = int(text)
    seconds = mins * 60
    
    update_auto_delete_timer(seconds)
    
    await update.message.reply_text(f"✅ Global Timer updated to **{mins} minutes**.", parse_mode="Markdown")
    return await show_settings_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    from handlers.admin import admin_dashboard
    await admin_dashboard(update, context)
    return ConversationHandler.END

settings_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^⚙️ Settings$"), settings_dashboard)],
    states={
        SELECT_SETTING: [
            MessageHandler(filters.Regex("^📝 Edit Message Template$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔗 Edit Help Link$"), handle_setting_selection),
            MessageHandler(filters.Regex("^📢 Edit Main Channel Template$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔐 Manage Force Subscribe$"), handle_setting_selection),
            MessageHandler(filters.Regex("^⏱️ Edit Global Timer$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔒 Toggle Content Protection$"), handle_setting_selection),
            MessageHandler(filters.Regex("^👋 Edit Welcome Message$"), handle_setting_selection),
            MessageHandler(filters.Regex("^🔙 Back to Dashboard$"), handle_setting_selection)
        ],
        EDIT_MSG_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_msg_template)],
        EDIT_HELP_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_help_link)],
        EDIT_WELCOME_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_welcome_message)],
        EDIT_MAIN_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_main_template)],
        
        MANAGE_FORCE_SUB: [
            MessageHandler(filters.Regex("^➕ Add Channel$"), handle_fs_action),
            MessageHandler(filters.Regex("^🔙 Back$"), handle_fs_action),
            CallbackQueryHandler(remove_fs_callback, pattern="^fs_rem_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), guide_fs_action)
        ],
        ADD_FS_CHANNEL: [MessageHandler((filters.TEXT | filters.FORWARDED) & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), add_fs_channel)],
        EDIT_GLOBAL_TIMER: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_REGEX), save_global_timer)]
    },
    fallbacks=[
        MessageHandler(filters.Regex(MENU_REGEX), global_fallback),
        CommandHandler("cancel", cancel)
    ],
    allow_reentry=True
)
