import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    ContextTypes,
)

# Testing Bot Token
BOT_TOKEN = "9065028572:AAE2ta4QkUt7xbAADfzWeX8XQh2B_lbPf1o"

# Render / Local port
PORT = int(os.getenv("PORT", "10000"))

# Apni Telegram User ID yahan daalein (jaise 123456789) taaki /setmsg kaam kare
ADMIN_USER_IDS = {
    int(uid.strip())
    for uid in os.getenv("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
}

# Default welcome message (runtime me /setmsg se badal sakte hain)
WELCOME_MESSAGE = os.getenv(
    "WELCOME_MESSAGE",
    "Thanks for joining {first_name}! 🎉"
)

# Request auto-approve karna ho to "true" karein
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "false").lower() == "true"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "बॉट चालू है! चैनल की join request आने पर कस्टम मैसेज भेजेगा।"
        )


async def set_msg_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global WELCOME_MESSAGE
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("❌ सिर्फ़ Admin ही मैसेज बदल सकता है।")
        return

    new_msg = " ".join(context.args).strip()
    if not new_msg:
        if update.message:
            await update.message.reply_text(
                "इस्तेमाल: `/setmsg Thanks for joining {first_name}!`"
            )
        return

    WELCOME_MESSAGE = new_msg
    if update.message:
        await update.message.reply_text(f"✅ नया मैसेज सेट हो गया:\n\n{WELCOME_MESSAGE}")


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if not req:
        return

    user = req.from_user
    chat = req.chat

    try:
        msg = WELCOME_MESSAGE.format(
            name=user.full_name or "User",
            first_name=user.first_name or "User",
            channel=chat.title or "Channel",
        )
    except Exception:
        msg = WELCOME_MESSAGE

    try:
        await context.bot.send_message(chat_id=user.id, text=msg)
        print(f"[DM SENT] User: {user.id} ({user.full_name}) | Chat: {chat.title}")
    except Exception as e:
        print(f"[DM FAILED] User: {user.id} | Error: {e}")

    if AUTO_APPROVE:
        try:
            await req.approve()
            print(f"[APPROVED] User: {user.id} in {chat.title}")
        except Exception as e:
            print(f"[APPROVE FAILED] User: {user.id} | Error: {e}")


# --- Render / Health Server ---
async def health_handler(request: web.Request) -> web.Response:
    return web.Response(text="Bot is running!")


async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get("/", health_handler)
    app_web.router.add_get("/health", health_handler)

    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[WEB] Listening on port {PORT}")


async def main():
    await start_web_server()

    tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start_cmd))
    tg_app.add_handler(CommandHandler("setmsg", set_msg_cmd))
    tg_app.add_handler(ChatJoinRequestHandler(handle_join_request))

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(
        allowed_updates=["message", "chat_join_request"]
    )
    print("[BOT] Polling started...")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
