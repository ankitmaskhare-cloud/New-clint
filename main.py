import os
import re
import asyncio
import logging
import sqlite3
import threading
from flask import Flask, request

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# ================= CONFIGURATION =================
BOT_TOKEN = "8800112468:AAHzOYXA3obKpJxhHwILsxaHOn_2WNLhl3E"
OWNER_ID = 8498419947
API_ID = 37344308
API_HASH = "9d7572be2c44f726721ab4d1ba2e2bcd"
# =================================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
bot_app = Application.builder().token(BOT_TOKEN).build()

# ================= MEMORY & STATE =================
WAITING_PHONE, WAITING_OTP, WAITING_2FA = range(3)
temp_login = {}

# ================= DATABASE (SQLite) =================
def init_db():
    conn = sqlite3.connect("accounts.db", timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        phone TEXT UNIQUE, name TEXT, user_id INTEGER, session_string TEXT, is_active INTEGER)""")
    conn.commit()
    conn.close()

def save_account(phone, name, user_id, session_string):
    conn = sqlite3.connect("accounts.db", timeout=30)
    conn.execute("""INSERT INTO accounts (phone, name, user_id, session_string, is_active) 
                 VALUES (?, ?, ?, ?, 1) ON CONFLICT(phone) DO UPDATE SET session_string=excluded.session_string""", 
                 (phone, name, user_id, session_string))
    conn.commit()
    conn.close()

init_db()

# ================= BOT MENU UI =================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Account", callback_data="add_acc")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ])

async def send_typing(context, chat_id):
    try: await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    except: pass

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await send_typing(context, update.effective_chat.id)
    await update.message.reply_text("👋 *Welcome to OTP Bot Manager!*\n\nYahan se apna account login karein.", parse_mode="Markdown", reply_markup=main_menu())

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await query.edit_message_text("1. Add Account par click karein.\n2. Apna number daalein.\n3. OTP daalein.\nBas account login ho jayega!", reply_markup=main_menu())

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📱 *Apna Phone Number daalein (Country code ke saath):*\nExample: `+919876543210`\n\nCancel karne ke liye /cancel likhein.", parse_mode="Markdown")
    return WAITING_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user_id = update.effective_user.id
    await update.message.delete()
    
    if not re.match(r"^\+\d{10,15}$", phone):
        await context.bot.send_message(update.effective_chat.id, "❌ Format galat hai. Dubara daalein (jaise +91...):")
        return WAITING_PHONE

    msg = await context.bot.send_message(update.effective_chat.id, f"⏳ `{phone}` par OTP bheja ja raha hai...", parse_mode="Markdown")
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    try:
        sent = await client.send_code_request(phone)
        temp_login[user_id] = {"phone": phone, "hash": sent.phone_code_hash, "client": client, "msg_id": msg.message_id}
        await msg.edit_text("📩 *OTP aapke Telegram par aaya hai. Yahan daalein:*", parse_mode="Markdown")
        return WAITING_OTP
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def get_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    user_id = update.effective_user.id
    await update.message.delete()
    
    data = temp_login.get(user_id)
    if not data:
        await context.bot.send_message(update.effective_chat.id, "❌ Session expire ho gaya. /start karein.")
        return ConversationHandler.END

    msg = await context.bot.send_message(update.effective_chat.id, "⏳ OTP Verify ho raha hai...")
    client = data["client"]
    
    try:
        await client.sign_in(data["phone"], otp, phone_code_hash=data["hash"])
        me = await client.get_me()
        session_str = client.session.save()
        
        save_account(data["phone"], me.first_name, me.id, session_str)
        await client.disconnect()
        
        await msg.edit_text(f"✅ *Login Successful!*\nName: {me.first_name}\nNumber: {data['phone']}\n\nAb aapka account bot ke saath connect ho gaya hai.", parse_mode="Markdown", reply_markup=main_menu())
        del temp_login[user_id]
        return ConversationHandler.END
    except SessionPasswordNeededError:
        await msg.edit_text("🔐 *2FA Password daalein:*", parse_mode="Markdown")
        return WAITING_2FA
    except PhoneCodeInvalidError:
        await msg.edit_text("❌ OTP galat hai. Dubara daalein:")
        return WAITING_OTP
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def get_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pwd = update.message.text.strip()
    user_id = update.effective_user.id
    await update.message.delete()
    
    data = temp_login.get(user_id)
    if not data: return ConversationHandler.END

    msg = await context.bot.send_message(update.effective_chat.id, "⏳ 2FA Verify ho raha hai...")
    client = data["client"]
    try:
        await client.sign_in(password=pwd)
        me = await client.get_me()
        session_str = client.session.save()
        
        save_account(data["phone"], me.first_name, me.id, session_str)
        await client.disconnect()
        
        await msg.edit_text(f"✅ *Login Successful (2FA)!*\nName: {me.first_name}\nNumber: {data['phone']}", parse_mode="Markdown", reply_markup=main_menu())
        del temp_login[user_id]
        return ConversationHandler.END
    except Exception as e:
        await msg.edit_text(f"❌ 2FA Error: {e}")
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancel ho gaya.", reply_markup=main_menu())
    return ConversationHandler.END

# Register Handlers
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CallbackQueryHandler(menu_callback, pattern="^help$"))
bot_app.add_handler(ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add, pattern="^add_acc$")],
    states={
        WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
        WAITING_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_otp)],
        WAITING_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_2fa)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
))

# ================= FLASK ROUTES =================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    asyncio.run_coroutine_threadsafe(bot_app.update_queue.put(update), bot_app.loop)
    return "OK", 200

@app.route("/")
def index():
    return "Bot is running perfectly!", 200

# ================= BOT STARTUP =================
async def start_bot():
    await bot_app.initialize()
    await bot_app.start()
    
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/{BOT_TOKEN}"
        await bot_app.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set to {webhook_url}")

def run_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot_app.loop = loop
    loop.run_until_complete(start_bot())
    loop.run_forever()

if __name__ == "__main__":
    threading.Thread(target=run_bot_thread, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
