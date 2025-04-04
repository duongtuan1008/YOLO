import asyncio
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "7251951915:AAFnZmCIxuMGr_MFe83C9PWoMnNB1_j0k8M"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Your chat ID is: {chat_id}")
    print(f"[DEBUG] CHAT ID: {chat_id}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.run_polling()
