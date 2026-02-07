import os
import re
import time
import asyncio
import requests
import random

from dotenv import load_dotenv
from supabase import create_client, Client

from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
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
# ADS TIMER SYSTEM
# =========================
ads_timer = {}
ADS_DURATION = 10


# =========================
# KEYBOARD MENU
# =========================
def main_keyboard():

    keyboard = [
        [
            KeyboardButton("👤 Account"),
            KeyboardButton("⭐ Premium")
        ]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        is_persistent=True   # FIXED
    )


# =========================
# USER SYSTEM
# =========================
def get_user(user):

    result = supabase.table("users") \
        .select("*") \
        .eq("id", user.id) \
        .execute()

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

    supabase.rpc(
        "increment_download",
        {"uid": user_id}
    ).execute()


# =========================
# ADS LINK
# =========================
def get_ads():

    result = supabase.table("ads_links") \
        .select("url") \
        .eq("active", True) \
        .execute()

    if result.data:
        return random.choice(result.data)["url"]

    return "https://example.com"


# =========================
# ANTI SPAM
# =========================
cooldown = {}

def is_spam(user_id):

    now = time.time()

    if user_id in cooldown:

        diff = now - cooldown[user_id]

        if diff < 5:
            return 5 - diff

    cooldown[user_id] = now

    return 0


# =========================
# LOADING UI
# =========================
async def show_progress(msg):

    steps = [
        "🔍 Mendapatkan info...",
        "📡 Menghubungi server...",
        "⚙️ Memproses media...",
        "📦 Menyiapkan opsi..."
    ]

    for step in steps:
        try:
            await msg.edit_text(step)
            await asyncio.sleep(0.5)
        except:
            break


# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    get_user(update.effective_user)

    await update.message.reply_text(
        "📥 Kirim link TikTok untuk mulai download",
        reply_markup=main_keyboard()
    )


# =========================
# ACCOUNT MENU
# =========================
async def show_account(update: Update):

    user = get_user(update.effective_user)

    status = "Premium" if user["premium"] else "Free"

    since = user.get("premium_since")
    expired = user.get("premium_expired")

    since_text = str(since)[:10] if since else "-"
    expired_text = str(expired)[:10] if expired else "-"

    await update.message.reply_text(
        f"👤 Account\n\n"
        f"ID: {update.effective_user.id}\n"
        f"Status: {status}\n"
        f"Aktif sejak: {since_text}\n"
        f"Berakhir: {expired_text}"
    )


# =========================
# PREMIUM MENU
# =========================
async def show_premium(update: Update):

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💳 Beli Premium Rp15.000 / bulan",
                callback_data="buy_premium"
            )
        ]
    ])

    await update.message.reply_text(
        "⭐ Premium Plan\n\n"
        "• Tanpa iklan\n"
        "• Download tanpa gangguan\n"
        "• Prioritas kecepatan\n\n"
        "Harga: Rp15.000 / bulan",
        reply_markup=keyboard
    )


# =========================
# TRIPAY CREATE
# =========================
def create_tripay(user_id):

    api_key = os.getenv("TRIPAY_API_KEY")

    data = {
        "method": "QRIS",
        "merchant_ref": f"PREMIUM-{user_id}-{int(time.time())}",
        "amount": 15000,
        "customer_name": str(user_id),
        "order_items": [
            {
                "name": "Premium 1 Bulan",
                "price": 15000,
                "quantity": 1
            }
        ]
    }

    headers = {
        "Authorization": "Bearer " + api_key
    }

    r = requests.post(
        "https://tripay.co.id/api/transaction/create",
        json=data,
        headers=headers
    )

    return r.json()


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


    user = update.effective_user

    cooldown_time = is_spam(user.id)

    if cooldown_time > 0:

        await update.message.reply_text(
            f"⏳ Tunggu {int(cooldown_time)} detik"
        )
        return


    url = extract_url(text)

    if not url:
        return


    msg = await update.message.reply_text("⏳ Memproses...")

    progress = asyncio.create_task(show_progress(msg))


    try:

        res = requests.get(API_URL, params={"url": url})

        json_data = res.json()

        if json_data["code"] != 0:

            await msg.edit_text("❌ Tidak dapat mengambil media")
            return


        data = json_data["data"]
        context.user_data["data"] = data

        progress.cancel()


        if data.get("images"):

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🖼️ Download Gambar", callback_data="check_images"),
                    InlineKeyboardButton("🎵 Download MP3", callback_data="check_mp3")
                ]
            ])

            await msg.edit_text("📸 Slide terdeteksi", reply_markup=keyboard)

        else:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📹 Download MP4", callback_data="check_mp4"),
                    InlineKeyboardButton("🎵 Download MP3", callback_data="check_mp3")
                ]
            ])

            await msg.edit_text("🎥 Video terdeteksi", reply_markup=keyboard)


    except:

        progress.cancel()
        await msg.edit_text("❌ Error")


# =========================
# HANDLE BUTTON
# =========================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    choice = query.data
    user = get_user(query.from_user)
    user_id = query.from_user.id


    if choice == "buy_premium":

        trx = create_tripay(user_id)

        pay_url = trx["data"]["checkout_url"]

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Bayar Sekarang", url=pay_url)]
        ])

        await query.message.reply_text(
            "Klik tombol untuk bayar:",
            reply_markup=keyboard
        )
        return


    if choice.startswith("check_"):

        format_choice = choice.replace("check_", "")
        context.user_data["format"] = format_choice

        # premium atau first download skip ads
        if user["premium"] or user["download_count"] == 0:

            await start_download_process(query, context)
            return


        ads = get_ads()

        ads_timer[user_id] = time.time()

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬇️ Download", url=ads)
            ]
        ])

        await query.message.reply_text(
            "⬇️ Menyiapkan download...\n"
            "Silakan tunggu 10 detik di halaman download",
            reply_markup=keyboard
        )

        asyncio.create_task(wait_and_send(query, context, user_id))


# =========================
# TIMER
# =========================
async def wait_and_send(query, context, user_id):

    await asyncio.sleep(ADS_DURATION)

    if user_id not in ads_timer:
        return

    await start_download_process(query, context)

    del ads_timer[user_id]


# =========================
# DOWNLOAD PROCESS
# =========================
async def start_download_process(query, context):

    msg = await query.message.reply_text("⏳ Memulai download...")

    steps = [
        "📡 Menghubungi server...",
        "📦 Mengambil file...",
        "⬇️ Mengirim file..."
    ]

    for step in steps:
        await asyncio.sleep(0.8)
        await msg.edit_text(step)

    await send_file(query, context)

    await msg.delete()


# =========================
# SEND FILE
# =========================
async def send_file(query, context):

    data = context.user_data.get("data")
    format_choice = context.user_data.get("format")

    increment_download(query.from_user.id)

    if format_choice == "mp4":
        await query.message.reply_video(data["play"])

    elif format_choice == "mp3":
        await query.message.reply_audio(data["music"])

    elif format_choice == "images":
        media = [InputMediaPhoto(x) for x in data["images"]]
        await query.message.reply_media_group(media)


# =========================
# MAIN
# =========================
def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(handle_button))

    print("Bot running successfully")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
