import os
import json
import asyncio
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Config ---
TITLE = os.getenv("TITLE", "Yaarwin")
BOT_TOKEN = os.getenv("BOT_TOKEN", "9065028572:AAE2ta4QkUt7xbAADfzWeX8XQh2B_lbPf1o").strip()
API_ID = int(os.getenv("API_ID", "37344308"))
API_HASH = os.getenv("API_HASH", "9d7572be2c44f726721ab4d1ba2e2bcd").strip()
PORT = int(os.getenv("PORT", "10000"))

# Agar ADMIN_USER_IDS khali hai, to jo pehla user /login ya /setmsg karega wahi admin ban jayega
ADMIN_USER_IDS = {
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
}

STATE_FILE = "state.json"

STATE = {
    "string_session": os.getenv("TG_STRING_SESSION", "").strip(),
    "welcome_message": os.getenv(
        "WELCOME_MESSAGE",
        f"Thanks for joining {{first_name}}! Welcome to {TITLE} 🎉"
    ),
    "dm_delay": float(os.getenv("DM_DELAY_SECONDS", "4")),
}

user_client: TelegramClient | None = None
dm_lock = asyncio.Lock()

# Pending login state per admin user_id
# step: "phone" | "otp" | "2fa"
pending_logins: dict[int, dict] = {}


def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(STATE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[STATE SAVE ERROR] {e}")


def load_state():
    global STATE
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                STATE.update({k: v for k, v in data.items() if v is not None})
        except Exception as e:
            print(f"[STATE LOAD ERROR] {e}")


def is_admin(user_id: int) -> bool:
    if not ADMIN_USER_IDS:
        ADMIN_USER_IDS.add(user_id)
        return True
    return user_id in ADMIN_USER_IDS


async def set_active_user_client(string_session: str) -> tuple[bool, str]:
    global user_client
    if not string_session:
        return False, "Session खाली है।"

    new_client = TelegramClient(StringSession(string_session), API_ID, API_HASH)
    await new_client.connect()
    if not await new_client.is_user_authorized():
        await new_client.disconnect()
        return False, "Session authorized नहीं है।"

    if user_client:
        try:
            await user_client.disconnect()
        except Exception:
            pass

    user_client = new_client
    STATE["string_session"] = string_session
    save_state()

    me = await user_client.get_me()
    return True, f"✅ Logged in as: {me.first_name} ({me.id})"


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        f"👋 *{TITLE}*\n\n"
        f"Commands:\n"
        f"• `/login` — बॉट में ही अपनी Telegram ID लॉगिन करें\n"
        f"• `/setmsg <text>` — Join request का मैसेज सेट करें\n"
        f"• `/status` — लॉगिन और मौजूदा मैसेज देखें\n"
        f"• `/cancel` — चल रही लॉगिन प्रक्रिया रद्द करें",
        parse_mode="Markdown",
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not is_admin(user.id) or not update.message:
        return

    logged_in = False
    who = "Not logged in"
    if user_client and user_client.is_connected() and await user_client.is_user_authorized():
        me = await user_client.get_me()
        logged_in = True
        who = f"{me.first_name} ({me.id})"

    await update.message.reply_text(
        f"📊 *{TITLE} Status*\n"
        f"• User ID Login: `{'Active' if logged_in else 'Inactive'}` ({who})\n"
        f"• Delay: `{STATE['dm_delay']}s`\n"
        f"• Welcome Msg:\n{STATE['welcome_message']}",
        parse_mode="Markdown",
    )


async def login_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    if not is_admin(user.id):
        await update.message.reply_text("❌ सिर्फ़ Admin ही लॉगिन कर सकता है।")
        return

    # Purana temp client ho to band karein
    old = pending_logins.get(user.id)
    if old and old.get("client"):
        try:
            await old["client"].disconnect()
        except Exception:
            pass

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    pending_logins[user.id] = {
        "step": "phone",
        "client": client,
    }
    await update.message.reply_text(
        "📱 अपना **Phone Number** (country code के साथ, जैसे `+919876543210`) भेजें:\n"
        "रद्द करने के लिए `/cancel` भेजें।",
        parse_mode="Markdown",
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    pending = pending_logins.pop(user.id, None)
    if pending and pending.get("client"):
        try:
            await pending["client"].disconnect()
        except Exception:
            pass
    await update.message.reply_text("✅ प्रक्रिया रद्द कर दी गई।")


async def set_msg_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or not update.message:
        return
    if not is_admin(user.id):
        await update.message.reply_text("❌ सिर्फ़ Admin मैसेज बदल सकता है।")
        return

    new_msg = " ".join(context.args).strip()
    if not new_msg:
        await update.message.reply_text(
            "इस्तेमाल: `/setmsg Thanks for joining {first_name}!`"
        )
        return

    STATE["welcome_message"] = new_msg
    save_state()
    await update.message.reply_text(f"✅ नया मैसेज सेट हो गया:\n\n{STATE['welcome_message']}")


async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles phone, OTP, and 2FA password during /login flow."""
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    if not user or user.id not in pending_logins:
        return

    flow = pending_logins[user.id]
    step = flow["step"]
    client: TelegramClient = flow["client"]
    text = update.message.text.strip()

    try:
        if step == "phone":
            phone = text.replace(" ", "")
            await client.send_code_request(phone)
            flow["phone"] = phone
            flow["step"] = "otp"
            await update.message.reply_text(
                "🔐 **OTP** भेज दिया गया है। अपना OTP भेजें (यदि Telegram code `12345` आए तो `12345` भेजें):",
                parse_mode="Markdown",
            )

        elif step == "otp":
            otp = text.replace(" ", "")
            try:
                await client.sign_in(phone=flow["phone"], code=otp)
            except SessionPasswordNeededError:
                flow["step"] = "2fa"
                await update.message.reply_text(
                    "🔑 इस अकाउंट पर **2FA Password** लगा है। अपना Password भेजें:"
                )
                return

            saved_str = client.session.save()
            pending_logins.pop(user.id, None)
            await client.disconnect()

            ok, info = await set_active_user_client(saved_str)
            await update.message.reply_text(
                f"{info}\n\n"
                f"💡 Render restart होने पर session बचाए रखने के लिए इसे Env Var `TG_STRING_SESSION` में भी डाल सकते हैं:\n`{saved_str}`",
                parse_mode="Markdown",
            )

        elif step == "2fa":
            await client.sign_in(password=text)
            saved_str = client.session.save()
            pending_logins.pop(user.id, None)
            await client.disconnect()

            ok, info = await set_active_user_client(saved_str)
            await update.message.reply_text(
                f"{info}\n\n"
                f"💡 Render restart होने पर session बचाए रखने के लिए इसे Env Var `TG_STRING_SESSION` में भी डाल सकते हैं:\n`{saved_str}`",
                parse_mode="Markdown",
            )

    except Exception as e:
        pending_logins.pop(user.id, None)
        try:
            await client.disconnect()
        except Exception:
            pass
        await update.message.reply_text(f"❌ Login Failed: `{e}`\nफिर से शुरू करने के लिए `/login` भेजें।", parse_mode="Markdown")


async def send_dm_from_user_id(target_user_id: int, text: str):
    global user_client
    if not user_client:
        print("[USER DM FAILED] Koi User ID logged in nahi hai. Bot me /login karein.")
        return

    async with dm_lock:
        try:
            if not user_client.is_connected():
                await user_client.connect()

            await user_client.send_message(target_user_id, text)
            print(f"[USER DM SENT] ({TITLE}) User ID -> {target_user_id}")
            await asyncio.sleep(float(STATE["dm_delay"]))

        except FloodWaitError as e:
            print(f"[USER FLOODWAIT] {e.seconds}s wait kar raha hai...")
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            print(f"[USER DM FAILED] Target {target_user_id}: {e}")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if not req:
        return

    user = req.from_user
    chat = req.chat
    template = STATE["welcome_message"]

    try:
        msg = template.format(
            name=user.full_name or "User",
            first_name=user.first_name or "User",
            channel=chat.title or "Channel",
            title=TITLE,
        )
    except Exception:
        msg = template

    asyncio.create_task(send_dm_from_user_id(user.id, msg))


# --- Render Web Server ---
async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text=f"{TITLE} is running!")


async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/", health_handler)
    app_web.router.add_get("/health", health_handler)

    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[WEB] {TITLE} listening on port {PORT}")


async def main():
    load_state()
    await start_web_server()

    if STATE.get("string_session"):
        ok, info = await set_active_user_client(STATE["string_session"])
        print(f"[STARTUP SESSION] {info}")

    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start_cmd))
    tg_app.add_handler(CommandHandler("status", status_cmd))
    tg_app.add_handler(CommandHandler("login", login_cmd))
    tg_app.add_handler(CommandHandler("cancel", cancel_cmd))
    tg_app.add_handler(CommandHandler("setmsg", set_msg_cmd))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))
    tg_app.add_handler(ChatJoinRequestHandler(handle_join_request))

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(
        allowed_updates=["message", "chat_join_request"]
    )
    print(f"[BOT] {TITLE} ready! Use /login in bot DM to login User ID.")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        if user_client:
            await user_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
