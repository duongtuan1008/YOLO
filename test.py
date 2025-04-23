import RPi.GPIO as GPIO
from mfrc522 import MFRC522
import time

# Khởi tạo đối tượng MFRC522
reader = MFRC522()

try:
    print("🆔 Đang chờ thẻ RFID...")
    while True:
        status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status != reader.MI_OK:
            continue

        status, uid = reader.MFRC522_Anticoll()
        if status != reader.MI_OK:
            continue

        uid_bytes = uid[:4]
        print("Thẻ quét:", [f"{b:02X}" for b in uid_bytes])

        # Dừng giao tiếp với thẻ RFID
        reader.MFRC522_StopCrypto1()  # Dừng giao tiếp với thẻ RFID
        time.sleep(1)

except KeyboardInterrupt:
    print("Quá trình bị dừng.")
finally:
    GPIO.cleanup()
