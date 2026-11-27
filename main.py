import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from flask import Flask

# ================= CONFIGURATION =================
API_ID = 1234567  # Apna API ID yahan dalein
API_HASH = 'your_api_hash_here'  # Apna API Hash yahan dalein
STRING_SESSION = '1BVtsOK4B...'  # Jo string session aapne banaya, wo yahan dalein

# Aapki Owner ID (Optional, agar aapko khud ko notification chahiye ho toh)
OWNER_ID = 8498419947 
# =================================================

app = Flask(__name__)

# Telethon Client Setup
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

@client.on(events.ChatAction)
async def handler(event):
    # Check karein ki koi naya user join hua hai ya nahi
    if event.user_joined or event.user_added:
        user = await event.get_user()
        
        try:
            # User ko text message jayega (Bina kisi VC ke)
            await client.send_message(user.id, "thanks for joining")
            print(f"Message sent to user: {user.id}")
            
        except Exception as e:
            print(f"Message nahi ja paya: {e}")

@app.route("/")
def index():
    return "Userbot is running perfectly!"

if __name__ == "__main__":
    # Bot start karein
    client.start()
    print("Userbot started... Waiting for join requests.")
    
    # Render ke liye Flask app run karein
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
