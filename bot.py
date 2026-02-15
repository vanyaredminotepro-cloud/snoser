import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

PHOTO_URL = "https://upload.wikimedia.org/wikipedia/commons/2/23/Pig_in_a_bucket.jpg"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_photo(PHOTO_URL)


app = Application.builder().token(os.environ["TG_BOT_TOKEN"]).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
