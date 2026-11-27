import os
from flask import Flask, request, render_template_string, session, redirect, url_for
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)
app.secret_key = "super_secret_key_for_login" # Session ke liye

API_ID = 37344308
API_HASH = '9d7572be2c44f726721ab4d1ba2e2bcd'

# Global variables jo login ke baad set honge
client = None
phone_code_hash = None

# ================= HTML PAGES =================
LOGIN_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Telegram Login</title></head>
<body style="text-align:center; margin-top:50px; font-family:Arial;">
    <h2>Apne Account Se Login Karein</h2>
    <form method="POST" action="/send_code">
        <input type="text" name="phone" placeholder="+919876543210" required style="padding:10px; width:250px;"><br><br>
        <button type="submit" style="padding:10px 20px; background:#0088cc; color:white; border:none;">Send OTP</button>
    </form>
</body>
</html>
"""

OTP_PAGE = """
<!DOCTYPE html>
<html>
<head><title>Enter OTP</title></head>
<body style="text-align:center; margin-top:50px; font-family:Arial;">
    <h2>OTP Daalein</h2>
    <form method="POST" action="/verify">
        <input type="text" name="otp" placeholder="12345" required style="padding:10px; width:250px;"><br><br>
        <button type="submit" style="padding:10px 20px; background:#0088cc; color:white; border:none;">Verify & Start Bot</button>
    </form>
</body>
</html>
"""

# ================= ROUTES =================
@app.route('/')
def index():
    if 'logged_in' in session:
        return "Aap already login hain! Bot abhi active hai."
    return LOGIN_PAGE

@app.route('/send_code', methods=['POST'])
def send_code():
    global client, phone_code_hash
    phone = request.form['phone']
    
    # Client start karein (agar pehle se nahi hai)
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    client.connect()
    
    try:
        # OTP bhejein
        sent = client.send_code_request(phone)
        phone_code_hash = sent.phone_code_hash
        return OTP_PAGE
    except Exception as e:
        return f"Error: {e}"

@app.route('/verify', methods=['POST'])
def verify():
    global client, phone_code_hash
    otp = request.form['otp']
    
    # Agar pehle se login hai
    if 'logged_in' in session:
        return "Aap already login hain!"

    try:
        # OTP verify karein
        client.sign_in(phone_code_hash=phone_code_hash, phone_code=otp)
        session_string = client.session.save()
        
        # Session ko save karein taaki bot chale
        with open("session.txt", "w") as f:
            f.write(session_string)
        
        # Bot start karein
        start_bot_with_session(session_string)
        
        session['logged_in'] = True
        return "Login Successful! Ab aapka bot active hai. Aap tab band kar sakte hain."
    except Exception as e:
        return f"Login Failed: {e}"

# ================= BOT LOGIC =================
def start_bot_with_session(session_string):
    global client
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    
    @client.on(events.ChatAction)
    async def handler(event):
        if event.user_joined or event.user_added:
            user = await event.get_user()
            try:
                await client.send_message(user.id, "thanks for joining")
                print(f"Message sent to {user.id}")
            except Exception as e:
                print(f"Error: {e}")
    
    # Bot ko alag thread me chalayein taaki Flask block na ho
    import threading
    def run_client():
        client.start()
        client.run_until_disconnected()
    
    threading.Thread(target=run_client, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
