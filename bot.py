import os
import re
import requests
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

API_URL = "https://tikwm.com/api/"

# regex semua link tiktok
TIKTOK_REGEX = r"(https?://[^\s]*tiktok\.com[^\s]*)"


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "jika menurutmu bot ini membantu \nGive mimin kopi : https://clicky.id/kang-banjar/support/coffee\n\n📥 Kirim link TikTok\nSupport:\n• Video\n• Foto\n• Semua jenis link"
    )


# extract link dari text
def extract_tiktok_url(text):
    match = re.search(TIKTOK_REGEX, text)
    if match:
        return match.group(0)
    return None


# resolve short link
def resolve_redirect(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=10)
        return r.url
    except:
        return url


# handler utama
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    url = extract_tiktok_url(text)

    if not url:
        return

    msg = await update.message.reply_text("⏳ Mengambil media...")

    try:

        # resolve short link
        url = resolve_redirect(url)

        # call API
        res = requests.get(API_URL, params={"url": url}, timeout=30)
        json = res.json()

        if json["code"] != 0:
            await msg.edit_text("❌ Gagal mengambil media")
            return

        data = json["data"]

        # VIDEO
        if data.get("play"):
            await update.message.reply_video(
                video=data["play"],
                caption="✅ Video berhasil didownload \nSupport admin: https://clicky.id/kang-banjar/support/coffee"
            )

        # GAMBAR
        elif data.get("images"):

            media = []

            for img in data["images"]:
                media.append(InputMediaPhoto(img))

            await update.message.reply_media_group(media)

        # AUDIO fallback
        elif data.get("music"):
            await update.message.reply_audio(
                audio=data["music"],
                caption="🎵 Audio berhasil didownload \nSupport admin: https://clicky.id/kang-banjar/support/coffee"
            )

        else:
            await msg.edit_text("❌ Media tidak ditemukan")
            return

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")


# MAIN
def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
