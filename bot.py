from telegram import Update, ChatPermissions
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest
from collections import defaultdict
import re
import time
from datetime import timedelta
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Access Control
AUTHORIZED_IDS = [int(id) for id in os.getenv('AUTHORIZED_IDS', '').split(',') if id]
EXCLUDED_USER_IDS = {int(id) for id in os.getenv('EXCLUDED_USER_IDS', '').split(',') if id}

# Your bot token from environment variable
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Global Variables
session_active = False
user_messages = defaultdict(list)  # Tracks usernames and messages per user
link_count = defaultdict(set)  # Tracks unique links shared by each user
total_unique_links = 0  # Tracks the total number of unique links across all users
banned_users = set()  # Tracks banned users
muted_users = {}  # Tracks muted users {user_id: chat_id}
link_usernames = defaultdict(int)  # Tracks unique usernames and link counts globally
checked_users = set()  # Tracks users who sent text messages before /check
post_check_users = set()  # Tracks users who send messages after /check

# Function to extract usernames from URLs
def extract_usernames(text):
    return re.findall(r"https://x\.com/([^/]+)/status/\d+", text)

# Helper Functions
def is_authorized(user_id):
    return user_id in AUTHORIZED_IDS

def is_valid_user_id(context, args):
    return args and args[0].isdigit()

# Start Session Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global session_active, user_messages, link_count, total_unique_links, muted_users, banned_users
    if not is_authorized(update.effective_user.id):
        return

    if session_active:
        await update.message.reply_text("A session is already active. Use /end to end the current session before starting a new one.")
        return

    session_active = True
    user_messages.clear()
    link_count.clear()
    total_unique_links = 0
    muted_users.clear()
    banned_users.clear()
    await update.message.reply_text("🚨 SESSION STARTED 🚨\n📢 Drop your links ❤️")

# List Links Command
async def list_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id) or not session_active:
        return

    if not user_messages:
        await update.message.reply_text("No links recorded.")
        return

    response_lines = []
    double_links = []
    total_count = 0

    for i, (user_id, messages) in enumerate(user_messages.items(), start=1):
        if user_id in EXCLUDED_USER_IDS:  # Skip multiple specific IDs
            continue

        try:
            chat = await context.bot.get_chat(user_id)
            telegram_name = chat.username or chat.first_name or "Unknown"
        except:
            telegram_name = "Unknown"

        unique_usernames = set(messages)
        for username in unique_usernames:
            response_lines.append(f"{i}. 📬 Twitter ID: @{username}\n  ➡️ Telegram ID: @{telegram_name} \n")
            total_count += 1

        if len(messages) > 1:
            double_links.append(f"[{username}] ({len(messages)} times) @{telegram_name}  (User ID: {user_id})")

    if double_links:
        response_lines.append("\nDouble links:")
        for i, double_link in enumerate(double_links, start=1):
            response_lines.append(f"{i}) {double_link}")

    response_lines.append(f"\nTotal count: {total_count}")

    response = "\n".join(response_lines)

    for chunk in split_message(response):
        await update.message.reply_text(chunk)

# Count Total Links Command
async def total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global total_unique_links
    if not is_authorized(update.effective_user.id) or not session_active:
        return

    await update.message.reply_text(f"Total links shared: {total_unique_links}")

# Double Links Command
async def doublelinks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global link_count
    if not is_authorized(update.effective_user.id) or not session_active:
        return

    double_links = []
    for user_id, links in link_count.items():
        if len(links) > 1:
            try:
                chat = await context.bot.get_chat(user_id)
                username = chat.username or chat.first_name or "Unknown"
            except:
                username = "Unknown"
            double_links.append(f"User ID: {user_id}, Username: {username}, Links: {len(links)}")

    if not double_links:
        await update.message.reply_text("No users shared more than one unique link.")
    else:
        await update.message.reply_text("Users with multiple links:\n" + "\n".join(double_links))

# Check Messages Command
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global checked_users, post_check_users
    if not is_authorized(update.effective_user.id) or not session_active:
        return

    # Track users who sent messages before /check command
    checked_users = set(user_messages.keys())

    # Clear post_check_users (users who sent messages after /check)
    post_check_users.clear()

    await update.message.reply_text("Tracking started. Use /unsafelist to see the unsafe list.")

# Record Messages (Text and Media)
async def record_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global user_messages, post_check_users, checked_users, total_unique_links, link_count, muted_users, banned_users
    if not session_active:
        return

    user_id = update.effective_user.id

    if user_id in banned_users or user_id in muted_users:
        return

    # Process text messages only
    if update.message.text:
        message = update.message.text
        usernames = extract_usernames(message)
        links = {word for word in message.split() if word.startswith("http")}

        if usernames:
            for username in usernames:
                link_usernames[username] += 1
                user_messages[user_id].append(username)

        if links:
            new_links = links - link_count[user_id]
            link_count[user_id].update(new_links)
            total_unique_links += len(new_links)

        # Mark the user as done if they sent any message after /check
        if user_id in checked_users:
            post_check_users.add(user_id)

    # Media messages (photo, video, document)
    elif update.message.photo or update.message.video or update.message.document:
        # We don't count media messages in the unsafe list, but we mark them as "done"
        if user_id in checked_users:
            post_check_users.add(user_id)

# Unsafe List Command
async def unsafe_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global user_messages, post_check_users, checked_users
    if not is_authorized(update.effective_user.id) or not session_active:
        return

    unsafe_users = checked_users - post_check_users
    if not unsafe_users:
        await update.message.reply_text("Everyone is done!")
        return

    response_lines = []
    for i, (user_id, messages) in enumerate(user_messages.items(), start=1):
        if user_id in unsafe_users and user_id not in EXCLUDED_USER_IDS:
            try:
                chat = await context.bot.get_chat(user_id)
                telegram_name = chat.username or chat.first_name or "Unknown"
            except:
                telegram_name = "Unknown"
            response_lines.append(f"{i}) @{telegram_name}")
    
    if not response_lines:
        await update.message.reply_text("No unsafe users found.")
        return
    
    response = "Unsafe list:\n" + "\n".join(response_lines)
    
    # Split response into chunks of 3900 characters
    chunk_size = 3900
    for i in range(0, len(response), chunk_size):
        await update.message.reply_text(response[i:i + chunk_size])

# Ban User Command
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    if not is_valid_user_id(context, context.args):
        await update.message.reply_text("Please provide a valid user ID to ban.")
        return

    user_id = int(context.args[0])
    try:
        await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user_id)
        banned_users.add(user_id)
        await update.message.reply_text(f"User {user_id} has been removed and banned from the group.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban user {user_id}: {e}")

# Unban User Command
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    if not is_valid_user_id(context, context.args):
        await update.message.reply_text("Please provide a valid user ID to unban.")
        return

    user_id = int(context.args[0])
    try:
        await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user_id)
        if user_id in banned_users:
            banned_users.remove(user_id)
        await update.message.reply_text(f"User {user_id} has been unbanned and can rejoin the group.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban user {user_id}: {e}")

# muteall
async def muteall(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /muteall <duration> (e.g., /muteall 7h or /muteall 7d)")
        return

    duration_str = context.args[0]
    duration = parse_duration(duration_str)
    
    if duration is None:
        await update.message.reply_text("Invalid duration format. Use (e.g., 30m, 2h, 1d).")
        return

    unsafe_users = checked_users - post_check_users
    unsafe_users -= EXCLUDED_USER_IDS  # Exclude certain users

    if not unsafe_users:
        await update.message.reply_text("No unsafe users found to mute.")
        return

    muted_count = 0
    for user_id in unsafe_users:
        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
            muted_users[user_id] = update.effective_chat.id  # Store muted user
            muted_count += 1

            # Schedule unmute after duration
            asyncio.create_task(unmute_after_delay(context, user_id, update.effective_chat.id, duration))

        except Exception as e:
            await update.message.reply_text(f"Failed to mute user {user_id}: {e}")

    await update.message.reply_text(f"Muted {muted_count} users for {duration_str}.")

# Mute User Command
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /mute <user_id> <duration> (e.g., /mute 123456789 10h)")
        return

    user_id = context.args[0]
    duration_str = context.args[1]

    try:
        user_id = int(user_id)  # Ensure user_id is an integer
    except ValueError:
        await update.message.reply_text("Invalid user ID format.")
        return

    duration = parse_duration(duration_str)
    if duration is None:
        await update.message.reply_text("Invalid duration format. (e.g., 30m, 2h, 1d).")
        return

    muted_users[user_id] = update.effective_chat.id  # Store muted user

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        await update.message.reply_text(f"User {user_id} has been muted for {duration_str}.")

        asyncio.create_task(unmute_after_delay(context, user_id, update.effective_chat.id, duration))
    
    except Exception as e:
        await update.message.reply_text(f"Failed to mute user {user_id}: {e}")

def parse_duration(duration_str: str):
    try:
        unit = duration_str[-1]
        value = int(duration_str[:-1])

        if unit == 'm':
            return timedelta(minutes=value)
        elif unit == 'h':
            return timedelta(hours=value)
        elif unit == 'd':
            return timedelta(days=value)
    except ValueError:
        return None

async def unmute_after_delay(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int, duration: timedelta):
    """Unmutes the user after the specified duration by restoring all chat permissions."""
    await asyncio.sleep(duration.total_seconds())

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        muted_users.pop(user_id, None)  # Remove from muted list
    except Exception as e:
        print(f"Failed to unmute user {user_id}: {e}")

# Unmute User Command
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    if not is_valid_user_id(context, context.args):
        await update.message.reply_text("Please provide a valid user ID to unmute.")
        return

    user_id = int(context.args[0])
    if user_id in muted_users:
        muted_users.pop(user_id, None)

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await update.message.reply_text(f"User {user_id} has been unmuted.")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute user {user_id}: {e}")

# Reply Mute User
async def reply_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to mute them.")
        return

    user_to_mute = update.message.reply_to_message.from_user
    muted_users[user_to_mute.id] = update.effective_chat.id

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_to_mute.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
        await update.message.reply_text(f"User {user_to_mute.mention_html()} has been muted.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute user {user_to_mute.id}: {e}")

# Reply Unmute User
async def reply_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to unmute them.")
        return

    user_to_unmute = update.message.reply_to_message.from_user
    if user_to_unmute.id in muted_users:
        muted_users.pop(user_to_unmute.id, None)

    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=user_to_unmute.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await update.message.reply_text(f"User {user_to_unmute.mention_html()} has been unmuted.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed to unmute user {user_to_unmute.id}: {e}")

# Reply Ban User
async def reply_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to ban them.")
        return

    user_to_ban = update.message.reply_to_message.from_user
    banned_users.add(user_to_ban.id)

    try:
        await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_ban.id)
        await update.message.reply_text(f"User {user_to_ban.mention_html()} has been banned from the group.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban user {user_to_ban.id}: {e}")

# Reply Unban User Command
async def reply_unban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to unban them.")
        return

    user_to_unban = update.message.reply_to_message.from_user
    if user_to_unban.id in banned_users:
        banned_users.remove(user_to_unban.id)

    try:
        await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user_to_unban.id)
        await update.message.reply_text(f"User {user_to_unban.mention_html()} has been unbanned and can rejoin the group.", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Failed to unban user {user_to_unban.id}: {e}")

# End Session Command
async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global session_active
    if update.effective_user.id not in AUTHORIZED_IDS or not session_active:
        return

    session_active = False
    user_messages.clear()
    link_count.clear()
    total_unique_links = 0
    banned_users.clear()
    muted_users.clear()

    await update.message.reply_text("Session is ended. Use /start to begin a new session.")

# Lock Group Permissions Command
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    try:
        await context.bot.set_chat_permissions(
            chat_id=update.effective_chat.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
        )
        await update.message.reply_text("The group is now locked. No one can send messages.")
    except Exception as e:
        await update.message.reply_text(f"Failed to lock the group: {e}")

# Open Group for Text Messages Only Command
async def open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    try:
        await context.bot.set_chat_permissions(
            chat_id=update.effective_chat.id,
            permissions=ChatPermissions(can_send_messages=True),
        )
        await update.message.reply_text("The group is now open for text messages only.")
    except Exception as e:
        await update.message.reply_text(f"Failed to open the group for text messages: {e}")

# Open Group for All Permissions Command
async def open_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    try:
        await context.bot.set_chat_permissions(
            chat_id=update.effective_chat.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await update.message.reply_text("The group is now fully open for messages and media.")
    except Exception as e:
        await update.message.reply_text(f"Failed to open the group for all messages: {e}")

# Group Rules Command
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    group_rules = """
🚨 K.G.F LIKE💞 - FOLLOW CAREFULLY 🚨

🔹 1. Drop Your Tweet Link
   📍 When the slot time is announced, drop your Tweet link in the group.
   ⏳ Slots remain open for 60 minutes.

🔹 2. Complete the Tasks
   🌟 We will provide a TL ID where all tweets for the slot are retweeted.
   🗂️ Your task: Like❤️ anll tweets from top to bottom on the provided TL.

🔹 3. Submit Proof
   📹 After completing your tasks, record a screen recording 🎥 showing your actions.
   📝 Attach the recording with your list number and send it in the group.

⚠️ 4. Warning for Scammers
   🚫 No proof? No participation! Scammers will be banned permanently from the group.
   🚷 Banned members will not be allowed to join future slots.

🌟 Be serious, follow the rules, and enjoy growing your engagement! 💪✨
"""
    await update.message.reply_text(group_rules)

# Slot Timing Command
async def slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return

    slot_timing = """
 Quick ⚡ Like Session 3.0

🚨First Slot - 07:00 AM To 09:30 AM

🚨Second Slot - 10:00 AM To 12:30 PM

🚨Third Slot - 01:00 PM To 03:30 PM

🚨Fourth Slot - 04:00 PM To 06:30 PM

🚨Fifth Slot - 07:00 PM To 09:30 PM
"""
    await update.message.reply_text(slot_timing)

# Split Message Function to Chunk the Response
def split_message(text, chunk_size=4000):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]

# Main Function
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_messages))
    application.add_handler(CommandHandler("total", total))
    application.add_handler(CommandHandler("doublelinks", doublelinks))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("muteall", muteall))
    application.add_handler(CommandHandler("unsafelist", unsafe_list))
    application.add_handler(CommandHandler("end", end))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("slot", slot))
    application.add_handler(CommandHandler("lock", lock))
    application.add_handler(CommandHandler("open", open))
    application.add_handler(CommandHandler("openall", open_all))
    application.add_handler(CommandHandler("replymute", reply_mute))
    application.add_handler(CommandHandler("replyunmute", reply_unmute))
    application.add_handler(CommandHandler("replyban", reply_ban))
    application.add_handler(CommandHandler("replyunban", reply_unban))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL, record_message))

    # Add error handling for production
    try:
        print("Bot is starting...")
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
    except Exception as e:
        print(f"Bot crashed with error: {e}")

if __name__ == "__main__":
    main()
