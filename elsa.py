import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_server():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), RequestHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()



import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = "8855998132:AAFk39fNIxy51T539R3SIYLmXHgME_5cB3k"   # आपका टोकन
ADMIN_IDS = [8099984863]

# --- DATABASE SCHEMAS (In-Memory Simulation) ---
db = {
    "users": {},        # structure: {user_id: {bal, points, premium_until, protect_until, is_dead, ...}}
    "saved_media": {},  # structure: {command: {"file_id": str, "type": str}}
    "banned_users": set(),
    "groups": set()
}

# --- ELSA DIALOGUE ENGINE ---
def elsa_speak(key, **kwargs):
    dialogues = {
        "dead_target": "Arre! ❄️ {target} toh pehle se hi baraf ban chuka hai (dead)! Unhe boliyie /revive karne ko.",
        "killer_dead": "Aap khud freeze ho chuke ho! 🥶 Pehle /revive karke hosh me aao, tabhi kisi aur ka shikaar kar paoge.",
        "protected_target": "Thahro! 🛡️ {target} ke paas Arendelle ki magical ice shield hai. Aap unhe nuksaan nahi pahuncha sakte!",
        "kill_success": "Boom! ❄️💥 {killer} ne {target} ko freeze kar diya! Reward: ₹500 mere bank se aapko mile. ✨",
        "kill_premium": "👑 *Premium Elsa User Action!* 👑\nBoom! ❄️💥 {killer} ne {target} ko freeze kar diya! Reward: ₹500 transferred smoothly.",
        "revived": "Pure Arendelle ki garmash aapke sath hai! 🔥 Aap ₹400 dekar successfully revive ho chuke hain.",
        "no_money": "Arre re... ❄️ Khali haath aaye the, khali haath jaoge! Aapke wallet me is cheez ke liye insufficient balance hai.",
        "give_success": "Ice Magic Share! ✨ Aapne {target} ko ₹{amount} transfer kar diye hain! Wallet check karein.",
        "daily_claimed": "❄️ Yeh lijiye aapka daily award! Aapko ₹{amount} mile hain. Kal fir aana!",
        "weekly_claimed": "Royal Treasury Reward! 👑 Poore hafte ki mehnat ka inaam: ₹{amount} aapke account me credit ho gaya!"
    }
    return dialogues.get(key, "").format(**kwargs)

# --- REUSABLE UTILITY ENGINE ---
def init_player(user_id, username="User", name="Arendelle Citizen"):
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "bal": 1000,
            "points": 0,
            "premium_until": None,
            "protect_until": None,
            "is_dead": False,
            "username": username,
            "name": name,
            "last_daily": None,
            "last_weekly": None
        }

def is_premium(user_id):
    user = db["users"].get(user_id)
    if user and user["premium_until"]:
        if user["premium_until"] > datetime.now():
            return True
    return False

def is_protected(user_id):
    user = db["users"].get(user_id)
    if user and user["protect_until"]:
        if user["protect_until"] > datetime.now():
            return True
    return False

# --- COMMAND: /kill ---
async def kill_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    init_player(user.id, user.username, user.first_name)
    
    if db["users"][user.id]["is_dead"]:
        await update.message.reply_text(elsa_speak("killer_dead"))
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❄️ Kisi ke message par reply karke unhe freeze (/kill) kijiye!")
        return
        
    target = update.message.reply_to_message.from_user
    init_player(target.id, target.username, target.first_name)
    
    if is_protected(target.id) or is_premium(target.id):
        await update.message.reply_text(elsa_speak("protected_target", target=target.first_name))
        return
        
    if db["users"][target.id]["is_dead"]:
        await update.message.reply_text(elsa_speak("dead_target", target=target.first_name))
        return
        
    db["users"][target.id]["is_dead"] = True
    db["users"][user.id]["bal"] += 500
    db["users"][user.id]["points"] += 1
    
    if is_premium(user.id):
        msg = elsa_speak("kill_premium", killer=user.first_name, target=target.first_name)
    else:
        msg = elsa_speak("kill_success", killer=user.first_name, target=target.first_name)
        
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- COMMAND: /revive ---
async def revive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_player(user_id, update.effective_user.username, update.effective_user.first_name)
    
    if not db["users"][user_id]["is_dead"]:
        await update.message.reply_text("❄️ Aap toh pehle se hi zinda hain! Baraf pighlane ki koi zaroorat nahi.")
        return
        
    if db["users"][user_id]["bal"] < 400:
        await update.message.reply_text(elsa_speak("no_money"))
        return
        
    db["users"][user_id]["bal"] -= 400
    db["users"][user_id]["is_dead"] = False
    await update.message.reply_text(elsa_speak("revived"))

# --- COMMAND: /give ---
async def give_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_player(user_id, update.effective_user.username, update.effective_user.first_name)
    
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("❄️ Format: Reply to a message with /give [amount]", parse_mode="Markdown")
        return
        
    try:
        amount = int(context.args[0])
        if amount <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❄️ Sahi amount input kijiye!")
        return
        
    if db["users"][user_id]["bal"] < amount:
        await update.message.reply_text(elsa_speak("no_money"))
        return
        
    target = update.message.reply_to_message.from_user
    init_player(target.id, target.username, target.first_name)
    
    db["users"][user_id]["bal"] -= amount
    db["users"][target.id]["bal"] += amount
    await update.message.reply_text(elsa_speak("give_success", target=target.first_name, amount=amount))

# --- COMMAND: /gift (Owner Only) ---
async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_IDS:
        return
        
    if not update.message.reply_to_message or not context.args:
        await update.message.reply_text("❄️ Owner Magic Format: Reply with /gift [amount]")
        return
        
    try:
        amount = int(context.args[0])
    except ValueError:
        return
        
    target = update.message.reply_to_message.from_user
    init_player(target.id, target.username, target.first_name)
    
    db["users"][target.id]["bal"] += amount
    await update.message.reply_text(f"❄️ Custom Royal Gift! Owner ne *{target.first_name}* ko ₹{amount} gift kiye hain! ✨", parse_mode="Markdown")

# --- COMMANDS: /daily & /weekly ---
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_player(user_id, update.effective_user.username, update.effective_user.first_name)
    
    base_reward = 200
    if is_premium(user_id):
        base_reward *= 2
        
    db["users"][user_id]["bal"] += base_reward
    await update.message.reply_text(elsa_speak("daily_claimed", amount=base_reward))

async def weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    init_player(user_id, update.effective_user.username, update.effective_user.first_name)
    
    base_reward = 1500
    if is_premium(user_id):
        base_reward *= 2
        
    db["users"][user_id]["bal"] += base_reward
    await update.message.reply_text(elsa_speak("weekly_claimed", amount=base_reward))

# --- GLOBAL GROUP TRACKING ---
async def track_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        db["groups"].add(update.effective_chat.id)

async def broadcast_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_IDS or not update.message.reply_to_message:
        return
    
    source_msg = update.message.reply_to_message
    success_count = 0
    
    for u_id in list(db["users"].keys()):
        try:
            await context.bot.forward_message(chat_id=u_id, from_chat_id=update.effective_chat.id, message_id=source_msg.message_id)
            success_count += 1
        except Exception:
            continue
            
    await update.message.reply_text(f"❄️ Broadcast complete to {success_count} direct active users channels.")

async def broadcast_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_IDS or not update.message.reply_to_message:
        return
        
    source_msg = update.message.reply_to_message
    success_count = 0
    
    for chat_id in list(db["groups"]):
        try:
            await context.bot.forward_message(chat_id=chat_id, from_chat_id=update.effective_chat.id, message_id=source_msg.message_id)
            success_count += 1
        except Exception:
            continue
            
    await update.message.reply_text(f"❄️ Broadcast complete to {success_count} structural group deployments.")

# --- ACTION PLUG: /punch & /bite ---
async def execute_action_extended(update: Update, context: ContextTypes.DEFAULT_TYPE, cmd_key: str, fallback_txt: str):
    user = update.effective_user
    if not update.message.reply_to_message:
        await update.message.reply_text(f"❄️ Kisi ke message par reply karke apply karein!")
        return
        
    target = update.message.reply_to_message.from_user
    media = db["saved_media"].get(cmd_key)
    caption = f"❄️ *{user.first_name}* ne *{target.first_name}* ko {fallback_txt}! 🔥"
    
    if is_premium(user.id):
        caption += "\n👑 _Premium Elsa User Action!_"

    if media:
        if media["type"] == "animation":
            await update.message.reply_animation(animation=media["file_id"], caption=caption, parse_mode="Markdown")
        elif media["type"] == "photo":
            await update.message.reply_photo(photo=media["file_id"], caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")

async def punch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_action_extended(update, context, "punch", "ek jordar Mukka mara 👊")

async def bite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await execute_action_extended(update, context, "bite", "gusse me Kaat liya (bit) 🦷")

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Track active groups globally
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, track_groups), group=-1)

    # Economy Engine Handlers
    app.add_handler(CommandHandler("kill", kill_command))
    app.add_handler(CommandHandler("revive", revive_command))
    app.add_handler(CommandHandler("give", give_command))
    app.add_handler(CommandHandler("gift", gift_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("weekly", weekly_command))
    
    # Custom Action Extensions
    app.add_handler(CommandHandler("punch", punch_cmd))
    app.add_handler(CommandHandler("bite", bite_cmd))
    
    # Global Messaging Hubs (Owner Only)
    app.add_handler(CommandHandler("broadcast", broadcast_users))
    app.add_handler(CommandHandler("groups", broadcast_groups))

    print("❄️ Elsa Core Extension Module Loaded.")
    app.run_polling()

if __name__ == "__main__":
    main()
