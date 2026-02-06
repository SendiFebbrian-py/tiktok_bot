import os
import re
import time
import asyncio
import requests
from dotenv import load_dotenv

from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup
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

API_URL = "https://tikwm.com/api/"
TIKTOK_REGEX = r"(https?://[^\s]*tiktok\.com[^\s]*)"

# =========================
# ANTI SPAM
# =========================
USER_COOLDOWN = 5
user_last_request = {}


def is_spam(user_id):
    now = time.time()

    if user_id in user_last_request:
        diff = now - user_last_request[user_id]

        if diff < USER_COOLDOWN:
            return USER_COOLDOWN - diff

    user_last_request[user_id] = now
    return 0


# =========================
# LOADING PROGRESS
# =========================
async def show_progress(message):

    steps = [
        "🔍 Mendapatkan info...",
        "📡 Menghubungi server TikTok...",
        "⚙️ Memproses media...",
        "📦 Menyiapkan opsi download..."
    ]

    for step in steps:
        try:
            await message.edit_text(step)
            await asyncio.sleep(0.7)
        except:
            break


# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 Kirim link TikTok\n\n"
        "Support:\n"
        "• Video → MP4 / MP3\n"
        "• Slide → Gambar / MP3\n\n"
        "☕ Support admin:\n"
        "https://clicky.id/kang-banjar/support/coffee"
    )


# =========================
# Extract URL
# =========================
def extract_tiktok_url(text):

    match = re.search(TIKTOK_REGEX, text)

    if match:
        return match.group(0)

    return None


# =========================
# Resolve redirect
# =========================
def resolve_redirect(url):

    try:
        r = requests.get(url, allow_redirects=True, timeout=10)
        return r.url

    except:
        return url


# =========================
# HANDLE MESSAGE
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    # ANTI SPAM CHECK
    cooldown = is_spam(user_id)

    if cooldown > 0:
        await update.message.reply_text(
            f"⏳ Tunggu {int(cooldown)} detik sebelum request lagi"
        )
        return

    text = update.message.text

    url = extract_tiktok_url(text)

    if not url:
        return

    msg = await update.message.reply_text("⏳ Memulai...")

    # show progress animation
    progress_task = asyncio.create_task(show_progress(msg))

    try:

        url = resolve_redirect(url)

        res = requests.get(API_URL, params={"url": url}, timeout=30)

        json_data = res.json()

        if json_data["code"] != 0:
            await msg.edit_text("❌ Gagal mengambil media")
            return

        data = json_data["data"]

        # simpan data
        context.user_data["tiktok_data"] = data

        progress_task.cancel()

        # =========================
        # SLIDE
        # =========================
        if data.get("images"):

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🖼️ Download Gambar", callback_data="dl_images"),
                    InlineKeyboardButton("🎵 Download MP3", callback_data="dl_mp3")
                ]
            ])

            await msg.edit_text(
                "📸 Slide terdeteksi\nPilih format:",
                reply_markup=keyboard
            )

            return

        # =========================
        # VIDEO
        # =========================
        if data.get("play"):

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📹 Download MP4", callback_data="dl_mp4"),
                    InlineKeyboardButton("🎵 Download MP3", callback_data="dl_mp3")
                ]
            ])

            await msg.edit_text(
                "🎥 Video terdeteksi\nPilih format:",
                reply_markup=keyboard
            )

            return

        await msg.edit_text("❌ Media tidak ditemukan")

    except Exception as e:

        progress_task.cancel()

        await msg.edit_text(f"❌ Error: {e}")


# =========================
# HANDLE BUTTON
# =========================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = context.user_data.get("tiktok_data")

    if not data:
        await query.edit_message_text("❌ Data expired, kirim ulang link")
        return

    choice = query.data

    try:

        # MP4
        if choice == "dl_mp4":

            await query.message.reply_text("⬇️ Mengirim video...")

            await query.message.reply_video(
                video=data["play"],
                caption="✅ Video berhasil didownload\n\n☕ Support admin:\nhttps://clicky.id/kang-banjar/support/coffee"
            )

        # MP3
        elif choice == "dl_mp3":

            await query.message.reply_text("⬇️ Mengirim audio...")

            await query.message.reply_audio(
                audio=data["music"],
                caption="✅ Audio berhasil didownload\n\n☕ Support admin:\nhttps://clicky.id/kang-banjar/support/coffee"
            )

        # IMAGES
        elif choice == "dl_images":

            await query.message.reply_text("⬇️ Mengirim gambar...")

            media = []

            for img in data["images"]:
                media.append(InputMediaPhoto(img))

            await query.message.reply_media_group(media)

        await query.message.delete()

    except Exception as e:

        await query.message.reply_text(f"❌ Error: {e}")


# =========================
# MAIN
# =========================
def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    app.add_handler(
        CallbackQueryHandler(handle_button)
    )

    print("🤖 Bot running...")
    app.run_polling()


# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()
