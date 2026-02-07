import os
import re
import asyncio
import requests
import random
from datetime import datetime, timedelta, timezone

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
        [[KeyboardButton("👤 Account"), KeyboardButton("⭐ Premium")]],
        resize_keyboard=True
    )

# =========================
# USER SYSTEM
# =========================

def get_user(user):

    result = supabase.table("users").select("*").eq("id", user.id).execute()

    if result.data:

        user_data = result.data[0]

        # cek expire premium
        if user_data.get("premium_expired"):

            expire = datetime.fromisoformat(user_data["premium_expired"])

            if expire < datetime.now(timezone.utc):

                supabase.table("users").update({
                    "premium": False
                }).eq("id", user.id).execute()

                user_data["premium"] = False

        return user_data

    # create user baru
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

    result = supabase.table("users").select("download_count").eq("id", user_id).execute()

    if result.data:

        count = result.data[0]["download_count"] + 1

        supabase.table("users").update({
            "download_count": count
        }).eq("id", user_id).execute()

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

async def show_account(update: Update):

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

async def show_premium(update: Update):

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Beli Premium (50 Stars)", callback_data="buy_premium")]
    ])

    await update.message.reply_text(
        "⭐ Premium Plan\n\n"
        "• Tanpa iklan\n"
        "• Download instan\n"
        "• Kecepatan prioritas\n\n"
        "Harga: 50 Stars / bulan",
        reply_markup=keyboard
    )

# =========================
# SEND INVOICE (Telegram Stars)
# =========================

async def send_invoice(query, context):

    prices = [LabeledPrice("Premium 1 Bulan", 50)]

    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="Premium Bot",
        description="Premium aktif 30 hari",
        payload="premium",
        provider_token="",  # kosong wajib untuk Stars
        currency="XTR",     # XTR = Telegram Stars
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

    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=30)

    supabase.table("users").update({
        "premium": True,
        "premium_since": now.isoformat(),
        "premium_expired": expire.isoformat()
    }).eq("id", user_id).execute()

    await update.message.reply_text(
        "✅ Premium aktif selama 30 hari!\n\nTerima kasih telah mendukung bot ini ⭐"
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

    try:

        res = requests.get(API_URL, params={"url": url})
        json_data = res.json()

        if "data" not in json_data:
            await msg.edit_text("❌ Gagal mengambil media")
            return

        data = json_data["data"]

        context.user_data["data"] = data

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📹 MP4", callback_data="dl_mp4"),
                InlineKeyboardButton("🎵 MP3", callback_data="dl_mp3")
            ]
        ])

        await msg.edit_text("Pilih format:", reply_markup=keyboard)

    except Exception as e:

        await msg.edit_text("❌ Error mengambil media")

# =========================
# HANDLE BUTTON
# =========================

async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    # beli premium
    if query.data == "buy_premium":
        await send_invoice(query, context)
        return

    # lanjutkan download
    if query.data == "continue":
        await send_file(query, context)
        return

    user = get_user(query.from_user)

    context.user_data["format"] = query.data.replace("dl_", "")

    # premium atau download pertama skip ads
    if user["premium"] or user["download_count"] == 0:
        await send_file(query, context)
        return

    ads = get_ads()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ Buka Iklan", url=ads)],
        [InlineKeyboardButton("✅ Lanjutkan Download", callback_data="continue")]
    ])

    await query.message.reply_text(
        "Silakan buka iklan terlebih dahulu",
        reply_markup=keyboard
    )

# =========================
# SEND FILE
# =========================

async def send_file(query, context):

    data = context.user_data.get("data")

    if not data:
        await query.message.reply_text("Session expired, kirim link lagi")
        return

    format_choice = context.user_data.get("format")

    increment_download(query.from_user.id)

    if format_choice == "mp4":

        await query.message.reply_video(data["play"])

    elif format_choice == "mp3":

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

    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("Bot running with Telegram Stars + Ads system")

    app.run_polling()

# =========================

if __name__ == "__main__":
    main()
