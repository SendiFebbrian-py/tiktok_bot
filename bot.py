import os
import re
import time
import asyncio
import requests
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from supabase import create_client, Client

from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    LabeledPrice
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler
)

# =========================
# LOAD ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

API_URL = "https://tikwm.com/api/"
TIKTOK_REGEX = r"(https?://[^\s]*tiktok\.com[^\s]*)"

# =========================
# KEYBOARD MENU
# =========================

def main_keyboard():

    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("👤 Account"), KeyboardButton("⭐ Premium")]
        ],
        resize_keyboard=True
    )

# =========================
# USER SYSTEM
# =========================

def get_user(user):

    result = supabase.table("users").select("*").eq("id", user.id).execute()

    if result.data:
        return result.data[0]

    supabase.table("users").insert({
        "id": user.id,
        "username": user.username or "",
        "premium": False,
        "download_count": 0
    }).execute()

    return {
        "premium": False,
        "download_count": 0
    }


def increment_download(user_id):

    supabase.table("users").update({
        "download_count": supabase.rpc("increment_download", {"uid": user_id})
    })

# =========================
# ADS
# =========================

def get_ads():

    result = supabase.table("ads_links").select("url").eq("active", True).execute()

    if result.data:
        return random.choice(result.data)["url"]

    return "https://example.com"

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    get_user(update.effective_user)

    await update.message.reply_text(
        "📥 Kirim link TikTok untuk download",
        reply_markup=main_keyboard()
    )

# =========================
# ACCOUNT
# =========================

async def show_account(update):

    user = get_user(update.effective_user)

    status = "Premium ⭐" if user["premium"] else "Free"

    await update.message.reply_text(
        f"👤 Account\n\n"
        f"ID: {update.effective_user.id}\n"
        f"Status: {status}"
    )

# =========================
# PREMIUM MENU
# =========================

async def show_premium(update):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Beli Premium (15 Stars)", callback_data="buy_premium")]
    ])

    await update.message.reply_text(
        "⭐ Premium Plan\n\n"
        "• Tanpa iklan\n"
        "• Download instan\n"
        "• Akses penuh\n\n"
        "Harga: 15 Stars / bulan",
        reply_markup=keyboard
    )

# =========================
# SEND INVOICE (Stars)
# =========================

async def send_invoice(query, context):

    prices = [LabeledPrice("Premium 1 Bulan", 15)]

    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="Premium Bot",
        description="Premium 30 hari",
        payload="premium",
        provider_token="",
        currency="XTR",
        prices=prices
    )

# =========================
# PRE CHECKOUT
# =========================

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.pre_checkout_query.answer(ok=True)

# =========================
# PAYMENT SUCCESS
# =========================

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    now = datetime.utcnow()
    expire = now + timedelta(days=30)

    supabase.table("users").update({
        "premium": True,
        "premium_since": now.isoformat(),
        "premium_expired": expire.isoformat()
    }).eq("id", user_id).execute()

    await update.message.reply_text(
        "✅ Premium aktif selama 30 hari!"
    )

# =========================
# EXTRACT URL
# =========================

def extract_url(text):

    match = re.search(TIKTOK_REGEX, text)

    return match.group(0) if match else None

# =========================
# HANDLE MESSAGE
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    if text == "👤 Account":
        await show_account(update)
        return

    if text == "⭐ Premium":
        await show_premium(update)
        return

    url = extract_url(text)

    if not url:
        return

    msg = await update.message.reply_text("⏳ Memproses...")

    res = requests.get(API_URL, params={"url": url})

    data = res.json()["data"]

    context.user_data["data"] = data

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📹 MP4", callback_data="dl_mp4"),
            InlineKeyboardButton("🎵 MP3", callback_data="dl_mp3")
        ]
    ])

    await msg.edit_text("Pilih format:", reply_markup=keyboard)

# =========================
# HANDLE BUTTON
# =========================

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "buy_premium":

        await send_invoice(query, context)
        return

    user = get_user(query.from_user)

    context.user_data["format"] = query.data.replace("dl_", "")

    if user["premium"] or user["download_count"] == 0:

        await send_file(query, context)
        return

    ads = get_ads()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ Download", url=ads)],
        [InlineKeyboardButton("Lanjutkan", callback_data="continue")]
    ])

    await query.message.reply_text("Buka iklan dulu:", reply_markup=keyboard)

# =========================
# SEND FILE
# =========================

async def send_file(query, context):

    data = context.user_data["data"]
    format_choice = context.user_data["format"]

    if format_choice == "mp4":

        await query.message.reply_video(data["play"])

    else:

        await query.message.reply_audio(data["music"])

# =========================
# MAIN
# =========================

def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.add_handler(CallbackQueryHandler(handle_button))

    app.add_handler(PreCheckoutQueryHandler(precheckout))

    app.add_handler(
        MessageHandler(
            filters.SUCCESSFUL_PAYMENT,
            successful_payment
        )
    )

    print("Bot running with Telegram Stars")

    app.run_polling()

# =========================

if __name__ == "__main__":
    main()
