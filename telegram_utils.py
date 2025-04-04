# telegram_utils.py
from telegram import Bot
import asyncio

BOT_TOKEN = "7251951915:AAFnZmCIxuMGr_MFe83C9PWoMnNB1_j0k8M"  # Thay bằng token của bạn
CHAT_ID = "1854422668"  # Thay bằng CHAT ID thật (lấy bằng getUpdates hoặc bot debug)

bot = Bot(token=BOT_TOKEN)

async def send_telegram(photo_path):
    try:
        print(f"[DEBUG] Gửi ảnh: {photo_path}")
        with open(photo_path, "rb") as photo:
            await bot.send_photo(chat_id=CHAT_ID, photo=photo, caption="🚨 Có xâm nhập, nguy hiểm!")
        print("✅ Đã gửi ảnh cảnh báo qua Telegram")
    except Exception as e:
        print("❌ Lỗi gửi Telegram:", e)
