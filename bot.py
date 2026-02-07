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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

API_URL = "https://tikwm.com/api/"
TIKTOK_REGEX = r"(https?://[^\s]*tiktok\.com[^\s]*)"


# =========================
# USER FUNCTIONS
# =========================
def get_user(user):

    result = supabase.table("users") \
        .select("*") \
        .eq("id", user.id) \
        .execute()

    if result.data:

        return result.data[0]

    # create new user
    supabase.table("users").insert({
        "id": user.id,
        "username": user.username or "",
        "download_count": 0,
        "premium": False
    }).execute()

    return {
        "id": user.id,
        "premium": False,
        "download_count": 0
    }


def increment_download(user_id):

    supabase.rpc(
        "increment_download",
        {"uid": user_id}
    ).execute()


# =========================
# ADS SYSTEM
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
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    get_user(update.effective_user)

    await update.message.reply_text(
        "📥 Kirim link TikTok\n\n"
        "Download pertama gratis.\n"
        "Seterusnya harus lihat iklan atau premium."
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

    user = update.effective_user

    cooldown_time = is_spam(user.id)

    if cooldown_time > 0:

        await update.message.reply_text(
            f"Tunggu {int(cooldown_time)} detik"
        )

        return


    url = extract_url(update.message.text)

    if not url:
        return


    msg = await update.message.reply_text("Processing...")


    try:

        res = requests.get(API_URL, params={"url": url})

        json_data = res.json()

        if json_data["code"] != 0:

            await msg.edit_text("Error")

            return


        data = json_data["data"]

        context.user_data["data"] = data
        context.user_data["url"] = url


        if data.get("images"):

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Download Images", callback_data="check_images"),
                    InlineKeyboardButton("Download MP3", callback_data="check_mp3")
                ]
            ])

        else:

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Download MP4", callback_data="check_mp4"),
                    InlineKeyboardButton("Download MP3", callback_data="check_mp3")
                ]
            ])


        await msg.edit_text("Pilih format:", reply_markup=keyboard)


    except Exception as e:

        await msg.edit_text(str(e))


# =========================
# HANDLE BUTTON
# =========================
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    choice = query.data

    user = update.effective_user

    user_data = get_user(user)


    # =========================
    # CHECK ADS REQUIREMENT
    # =========================
    if choice.startswith("check_"):

        format_choice = choice.replace("check_", "")

        context.user_data["format"] = format_choice

        # premium skip ads
        if user_data["premium"]:

            await send_file(query, context)
            return

        # first download free
        if user_data["download_count"] == 0:

            await send_file(query, context)
            return

        # show ads
        ads = get_ads()

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Buka Iklan", url=ads)],
            [InlineKeyboardButton("Lanjutkan Download", callback_data="continue")]
        ])

        await query.message.reply_text(
            "Silakan buka iklan dulu:",
            reply_markup=keyboard
        )

        return


    if choice == "continue":

        await send_file(query, context)


# =========================
# SEND FILE
# =========================
async def send_file(query, context):

    data = context.user_data.get("data")
    format_choice = context.user_data.get("format")

    user_id = query.from_user.id

    increment_download(user_id)


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

    print("Bot running with premium + ads system")

    app.run_polling()


if __name__ == "__main__":
    main()
