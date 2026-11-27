import os
import telebot
from flask import Flask, request
from telebot.types import ChatJoinRequest

# ================= CONFIGURATION =================
BOT_TOKEN = "8800112468:AAHzOYXA3obKpJxhHwILsxaHOn_2WNLhl3E"
OWNER_USER_ID = 8498419947 
# =================================================

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Jab koi channel join request bhejega
@bot.chat_join_request_handler()
def handle_join_request(message: ChatJoinRequest):
    user = message.from_user
    
    # User ka username check karna
    user_username = f"@{user.username}" if user.username else "No Username"
    
    # Aapka exact message
    text = (
        f"Hy I am joining your team\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🔗 Username: {user_username}\n"
        f"🆔 User ID: {user.id}"
    )
    
    try:
        # Owner (Aap) ko DM bhejna
        bot.send_message(OWNER_USER_ID, text)
        print(f"Message sent to owner for user {user.id}")
    except Exception as e:
        print(f"Error: {e}")

# Render Webhook Setup
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    # Jab koi browser mein link kholega, bot ka webhook set ho jayega
    render_url = os.environ.get('RENDER_EXTERNAL_URL') # Render automatically yeh URL deta hai
    
    if render_url:
        bot.remove_webhook()
        bot.set_webhook(url=f"{render_url}/{BOT_TOKEN}")
        return f"Webhook set to {render_url}", 200
    else:
        return "Render URL not found. If testing locally, use polling.", 200

if __name__ == "__main__":
    # Local testing ke liye
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
