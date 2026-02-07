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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

API_URL = "https://tikwm.com/api/"
TIKTOK_REGEX = r"(https?://[^\s]*tiktok\.com[^\s]*)"


# =========================
# KEYBOARD MENU
# =========================

def main_keyboard(user_id):

    keyboard = [
        [KeyboardButton("👤 Account"), KeyboardButton("⭐ Premium")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton("🛠 Admin")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =========================
# USER SYSTEM
# =========================

def get_user(user):

    result = supabase.table("users").select("*").eq("id", user.id).execute()

    if result.data:

        user_data = result.data[0]

        if user_data.get("premium_expired"):

            expire = datetime.fromisoformat(user_data["premium_expired"])

            if expire < datetime.now(timezone.utc):

                supabase.table("users").update({
                    "premium": False
                }).eq("id", user.id).execute()

                user_data["premium"] = False

        return user_data

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

    result = supabase.table("users") \
        .select("download_count") \
        .eq("id", user_id) \
        .execute()

    if result.data:

        count = result.data[0]["download_count"] + 1

        supabase.table("users") \
            .update({"download_count": count}) \
            .eq("id", user_id) \
            .execute()


# =========================
# ADS SYSTEM
# =========================

def get_ads():

    result = supabase.table("ads_links") \
        .select("*") \
        .eq("active", True) \
        .execute()

    if result.data:
        return random.choice(result.data)["url"]

    return None


# kirim preview ads tanpa teks
async def send_ads_preview(chat):

    ad1 = get_ads()
    ad2 = get_ads()

    if ad1:
        await chat.reply_text(ad1)

    await asyncio.sleep(1)

    if ad2:
        await chat.reply_text(ad2)


# =========================
# ADMIN PANEL
# =========================

async def show_admin(update):

    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = ReplyKeyboardMarkup(
        [
            ["👥 Statistik Users"],
            ["➕ Tambah Ads"],
            ["📋 List Ads"],
            ["❌ Hapus Ads"],
            ["⬅️ Kembali"]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=keyboard
    )


async def show_stats(update):

    total_users = supabase.table("users") \
        .select("id", count="exact") \
        .execute()

    total_premium = supabase.table("users") \
        .select("id", count="exact") \
        .eq("premium", True) \
        .execute()

    await update.message.reply_text(
        f"📊 Statistik Bot\n\n"
        f"👥 Total Users: {total_users.count}\n"
        f"⭐ Premium Users: {total_premium.count}"
    )


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    get_user(update.effective_user)

    await update.message.reply_text(
        "📥 Kirim link TikTok untuk download",
        reply_markup=main_keyboard(update.effective_user.id)
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
        [InlineKeyboardButton(
            "⭐ Beli Premium (50 Stars)",
            callback_data="buy_premium"
        )]
    ])

    await update.message.reply_text(
        "⭐ Premium Plan\n\n"
        "• Tanpa iklan\n"
        "• Download instan\n"
        "• Prioritas kecepatan\n\n"
        "Harga: 50 Stars / bulan",
        reply_markup=keyboard
    )


# =========================
# TELEGRAM STARS PAYMENT
# =========================

async def send_invoice(query, context):

    prices = [LabeledPrice("Premium 1 Bulan", 50)]

    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="Premium Bot",
        description="Premium aktif 30 hari",
        payload="premium",
        provider_token="",
        currency="XTR",
        prices=prices
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):

    payload = update.message.successful_payment.invoice_payload

    if payload != "premium":
        return

    user_id = update.effective_user.id

    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=30)

    supabase.table("users").update({
        "premium": True,
        "premium_since": now.isoformat(),
        "premium_expired": expire.isoformat()
    }).eq("id", user_id).execute()

    await update.message.reply_text("✅ Premium aktif")


# =========================
# HANDLE MESSAGE
# =========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    user_id = update.effective_user.id

    if text == "👤 Account":
        await show_account(update)
        return

    if text == "⭐ Premium":
        await show_premium(update)
        return

    if text == "🛠 Admin":
        await show_admin(update)
        return

    if text == "👥 Statistik Users":
        if user_id == ADMIN_ID:
            await show_stats(update)
        return

    if text == "⬅️ Kembali":
        await update.message.reply_text(
            "Menu utama",
            reply_markup=main_keyboard(user_id)
        )
        return

    if text == "➕ Tambah Ads":
        context.user_data["admin_mode"] = "add_ads"
        await update.message.reply_text("Kirim link ads")
        return

    if text == "❌ Hapus Ads":
        context.user_data["admin_mode"] = "delete_ads"
        await update.message.reply_text("Kirim ID ads")
        return

    if text == "📋 List Ads":

        result = supabase.table("ads_links").select("*").execute()

        msg = "📋 List Ads\n\n"

        for ad in result.data:
            msg += f"{ad['id']} - {ad['url']}\n"

        await update.message.reply_text(msg)
        return

    if context.user_data.get("admin_mode") == "add_ads":

        supabase.table("ads_links").insert({
            "url": text,
            "active": True
        }).execute()

        context.user_data["admin_mode"] = None

        await update.message.reply_text("✅ Ads ditambahkan")
        return

    if context.user_data.get("admin_mode") == "delete_ads":

        supabase.table("ads_links") \
            .delete() \
            .eq("id", int(text)) \
            .execute()

        context.user_data["admin_mode"] = None

        await update.message.reply_text("✅ Ads dihapus")
        return

    url = re.search(TIKTOK_REGEX, text)

    if not url:
        return

    msg = await update.message.reply_text("⏳ Memproses...")

    res = requests.get(API_URL, params={"url": url.group(0)})
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

    # first download langsung
    if user["download_count"] == 0:
        await send_file(query, context)
        return

    # tampilkan ads jika free
    if not user["premium"]:
        await send_ads_preview(query.message)
        await asyncio.sleep(20)
    else:
        await asyncio.sleep(10)

    await send_file(query, context)


# =========================
# SEND FILE
# =========================

async def send_file(query, context):

    data = context.user_data.get("data")

    if not data:
        await query.message.reply_text("Session expired")
        return

    increment_download(query.from_user.id)

    if context.user_data["format"] == "mp4":
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

    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    print("Bot running FULL")

    app.run_polling()


if __name__ == "__main__":
    main()
