import RPi.GPIO as GPIO
import time
import cv2
import numpy as np
import mediapipe as mp
import time
import threading
from flask import Flask, Response
from yolodetect import YoloDetect
from picamera2 import Picamera2
from shapely.geometry import Point, Polygon
import joblib
import pandas as pd
import os
from datetime import datetime
import pytz
import queue  # Thêm cái này
import pigpio
import mimetypes
import smtplib
from email.message import EmailMessage
import imghdr
import requests  # Thêm dòng này nếu chưa có
import hashlib
import mysql.connector
from RPLCD.i2c import CharLCD
import mediapipe as mp
import math
import joblib
from mfrc522 import MFRC522
reader = MFRC522()  # nếu có tham số này
rfid_list = []
# Khởi tạo màn hình LCD
lcd = CharLCD('PCF8574', 0x27)  # Thay '0x27' bằng địa chỉ I2C của LCD (kiểm tra bằng lệnh i2cdetect)
# khai bao sender_email Reciever_Email và pass_sender 
Sender_email = "duongtuan10082003@gmail.com"
Reciever_Email ="duongtuan1008@gmail.com"
pass_sender = "vrrw tsqa aljl nbrk"

# Các chế độ mật khẩu
mode_changePass = "*#01#"
mode_resetPass = "*#02#"
mode_hardReset = "*#03#"
mode_addRFID = "*101#"
mode_delRFID = "*102#"
mode_delAllRFID = "*103#"


pi = pigpio.pi()

# Khởi tạo ThreadPoolExecutor với tối đa 2 luồng (mỗi servo một luồng)
servo_queue = queue.Queue()
GPIO.setwarnings(False)
# Cấu hình GPIO cho servo và đèn
servo_pin_1 = 17  # Pin servo 1
servo_pin_2 = 18  # Pin servo 2
light_pin = 23  # Pin đèn
auto_mode = True  # True: tự động theo người, False: điều khiển tay
current_angle_1 = 90  # Servo trục ngang
current_angle_2 = 90  # Servo trục dọc
is_yolo_active = True  # Bắt đầu với việc quét YOLO hoạt động


# Định nghĩa chân GPIO cho hàng và cột
ROW_PINS = [6, 13, 19, 26]  # Các chân cho hàng R1, R2, R3, R4
COL_PINS = [12, 16, 20, 21]  # Các chân cho cột C1, C2, C3, C4

GPIO.cleanup()
GPIO.setmode(GPIO.BCM)
RELAY_PIN = 27
BUZZER =25
GPIO.setup(BUZZER,GPIO.OUT)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(servo_pin_1, GPIO.OUT)
GPIO.setup(servo_pin_2, GPIO.OUT)
GPIO.setup(light_pin, GPIO.OUT)
pass_def = "12345"
mode_changePass = '*#01#'
mode_resetPass = '*#02#'
password_input = ''
key_queue = queue.Queue()
new_pass1 = [''] * 5
new_pass2 = [''] * 5
data_input = []
# Cập nhật để tránh tranh chấp tài nguyên
lock = threading.Lock()
KEYPAD = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]


# Hàm kiểm tra thẻ RFID có hợp lệ không
def is_rfid_allowed(uid_bytes):
    # Chuyển UID thành chuỗi hex
    uid_hex = ''.join([f"{b:02X}" for b in uid_bytes])  # Chuyển mỗi byte thành hex
    print(f"UID đã quét (hex): {uid_hex}")
    
    # Kiểm tra xem UID có tồn tại trong danh sách UID hợp lệ từ cơ sở dữ liệu không
    allowed_uids = load_rfid_list()  # Lấy danh sách UID từ cơ sở dữ liệu
    return uid_hex in allowed_uids

# Hàm lấy UID từ cơ sở dữ liệu
# Hàm lấy UID từ cơ sở dữ liệu
def load_rfid_list():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT uid1, uid2, uid3, uid4 FROM rfid_users")
        rows = cursor.fetchall()
        allowed_uids = []
        for row in rows:
            # Lưu UID dưới dạng chuỗi hex
            # Chuyển các phần tử từ chuỗi hex (16) thành số nguyên
            uid = ''.join([f"{int(row[i], 16):02X}" for i in range(4)])  # Chuyển từ hex (base 16) thành chuỗi hex
            allowed_uids.append(uid)
        cursor.close()
        conn.close()
        return allowed_uids
    except Exception as e:
        print("❌ Lỗi khi lấy UID từ DB:", e)
        return []


# Kết nối cơ sở dữ liệu
def connect_db():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",  # Thay bằng user MySQL của bạn
            password="100803",  # Thay bằng mật khẩu MySQL
            database="door_access"
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Lỗi kết nối MySQL: {err}")
        return None

# ========== RFID HANDLING ==========

def check_rfid_from_db():
    try:
        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, uid1, uid2, uid3, uid4 FROM rfid_users ORDER BY id ASC")
        rows = cursor.fetchall()
        print("📦 Danh sách RFID trong DB:")
        for row in rows:
            print(f"ID {row[0]}: {row[1]} {row[2]} {row[3]} {row[4]}")
        cursor.close()
        conn.close()
    except Exception as e:
        print("❌ Lỗi khi đọc RFID từ DB:", e)

def is_rfid_allowed(uid_bytes):
    # Chuyển UID thành chuỗi hex
    uid_hex = ''.join([f"{b:02X}" for b in uid_bytes])
    
    # Kiểm tra xem UID có tồn tại trong danh sách UID hợp lệ từ cơ sở dữ liệu không
    allowed_uids = load_rfid_list()  # Lấy danh sách UID từ cơ sở dữ liệu
    return uid_hex in allowed_uids

def check_rfid_once():
    global is_yolo_active

    while True:
        with lock:
            # Kiểm tra xem có thẻ RFID nào gần đầu đọc không
            status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
            if status != reader.MI_OK:
                continue  # Không có thẻ, tiếp tục quét

            # Lấy UID của thẻ RFID
            status, uid = reader.MFRC522_Anticoll()
            if status != reader.MI_OK:
                continue  # Không thể lấy UID thẻ, tiếp tục quét

            # Chuyển UID thành dạng hex để dễ kiểm tra
            uid_bytes = uid[:4]
            uid_hex = [f"{b:02X}" for b in uid_bytes]
            print("Thẻ quét:", uid_hex)

            # Hiển thị thông tin lên LCD
            lcd.clear()

            # Kiểm tra xem thẻ có hợp lệ không
            if is_rfid_allowed(uid_bytes):
                lcd.write_string("ACCESS GRANTED")
                GPIO.output(RELAY_PIN, GPIO.HIGH)  # Mở cửa
                log_access("RFID User", "RFID", "Mở cửa bằng thẻ")  # Ghi log
                time.sleep(5)  # Giữ cửa mở trong 5 giây
                GPIO.output(RELAY_PIN, GPIO.LOW)  # Đóng cửa

                # Tạm thời tắt YOLO để tránh quét đối tượng trong lúc mở cửa
                is_yolo_active = False
                time.sleep(5)  # Chờ 5 giây trước khi bật lại YOLO
                is_yolo_active = True  # Kích hoạt lại YOLO
            else:
                lcd.write_string("INVALID RFID")
                open_buzzer(1)  # Bật chuông cảnh báo
                SendEmail(Sender_email, pass_sender, Reciever_Email)  # Gửi email cảnh báo

            # Dừng giao tiếp với thẻ RFID sau khi quét xong
            reader.MFRC522_StopCrypto1()  # Dừng giao tiếp với thẻ RFID
            reset_lcd_to_default()  # Reset LCD

        # Thời gian chờ trước khi quét lại (điều chỉnh nếu cần)
        time.sleep(1)
  # Thời gian giữa các lần quét (có thể điều chỉnh)

# Hàm ghi log khi mở cửa bằng RFID
def log_access(user_name, access_method, event_description):
    # Logic ghi log vào cơ sở dữ liệu hoặc file
    print(f"Logged: {user_name} - {access_method} - {event_description}")

# Hàm chạy trong một luồng riêng
def run_rfid_thread():
    while True:
        check_rfid_once()
def wait_for_rfid(timeout=10):
    end_time = time.time() + timeout
    while time.time() < end_time:
        status, _ = reader.MFRC522_Request(reader.PICC_REQIDL)
        if status != reader.MI_OK:
            continue

        status, uid = reader.MFRC522_Anticoll()
        if status == reader.MI_OK:
            reader.MFRC522_StopCrypto1()  # Dòng s?a ? dây
            return [f"{b:02X}" for b in uid[:4]]
        time.sleep(0.3)
    return None
def read_keypad():
    for row in range(4):  # Loop through all rows
        GPIO.output(ROW_PINS[row], GPIO.HIGH)  # Activate the current row
        for col in range(4):  # Loop through all columns
            if GPIO.input(COL_PINS[col]) == GPIO.HIGH:  # Check if the key is pressed
                key = KEYPAD[row][col]
                GPIO.output(ROW_PINS[row], GPIO.LOW)  # Deactivate the row after key is detected
                return key  # Return the corresponding key
        GPIO.output(ROW_PINS[row], GPIO.LOW)  # Deactivate the row if no key is detected
    return None  # Return None if no key is pressed
def add_new_rfid():
    global id_rf
    lcd.clear()
    lcd.write_string("Nhap ID (1-99)")

    # Nhập ID từ bàn phím keypad
    id_rf = ''
    while len(id_rf) < 2:  # Giới hạn nhập ID chỉ gồm 2 chữ số
        key = read_keypad()
        if key:
            print(f"Key pressed: {key}")
            if key.isdigit():
                id_rf += key
                lcd.clear()
                lcd.write_string(f"ID: {id_rf}")
            elif key == '#':  # Nếu nhấn '#', xác nhận ID
                if id_rf.isdigit() and 0 < int(id_rf) <= 99:
                    break
                else:
                    lcd.clear()
                    lcd.write_string("ID ERROR")
                    time.sleep(2)
                    lcd.clear()
                    lcd.write_string("Nhap lai ID")
                    id_rf = ''
                    time.sleep(1)
            time.sleep(0.3)

    print(f"ID nhập: {id_rf}")
    lcd.clear()
    lcd.write_string("Quet the lan 1")
    print("🕐 Đưa thẻ lần 1...")
    first_uid = wait_for_rfid()
    if first_uid is None:
        lcd.clear()
        lcd.write_string("KHONG THE")
        time.sleep(2)
        return

    print("✅ UID 1:", first_uid)

    # --- Quét lần 2 ---
    lcd.clear()
    lcd.write_string("Quet the lan 2")
    print("🕐 Đưa thẻ lại lần 2...")
    second_uid = wait_for_rfid()
    if second_uid is None:
        lcd.clear()
        lcd.write_string("KHONG THE")
        time.sleep(2)
        return

    print("🔁 UID 2:", second_uid)

    if first_uid != second_uid:
        lcd.clear()
        lcd.write_string("KHONG TRUNG")
        print("⚠️ UID không trùng nhau!")
        time.sleep(2)
        return

    # Gửi lên server
    try:
        url = f"http://192.168.137.128/api/rfid.php?action=add"
        url += f"&id={id_rf}&uid1={first_uid[0]}&uid2={first_uid[1]}"
        url += f"&uid3={first_uid[2]}&uid4={first_uid[3]}"
        print("📡 Gửi:", url)
        r = requests.get(url)
        print("📨 Server:", r.text)
        lcd.clear()
        lcd.write_string("THEM OK")
        load_rfid_list()
    except:
        lcd.clear()
        lcd.write_string("LOI MANG")

    time.sleep(2)
    reset_lcd_to_default()
#------------keypad--------------------

def get_device_state():
    try:
        res = requests.get("http://192.168.137.128/api/servo_control.php?cmd=get_state", timeout=2)
        data = res.json()
        if data.get("status") == "success":
            return data["data"]  # {"auto": "on", "light": "off"}
    except Exception as e:
        print("❌ Không lấy được trạng thái từ PHP:", e)
    return {}
def read_auto_mode():
    try:
        with open("/home/pi/auto_mode.txt", "r") as f:
            return f.read().strip() == "on"
    except:
        return True


def log_access(user_name, access_method, event_description):
    conn = connect_db()
    if conn is None:
        print("⚠ Không thể kết nối MySQL, bỏ qua ghi nhật ký truy cập.")
        return
    
    try:
        cursor = conn.cursor()
        sql = "INSERT INTO access_log (user_name, access_method, event_description, timestamp) VALUES (%s, %s, %s, NOW())"
        values = (user_name, access_method, event_description)
        cursor.execute(sql, values)
        conn.commit()
        print(f"✅ Ghi nhật ký vào `access_log`: {user_name} - {access_method}")
    except mysql.connector.Error as err:
        print(f"❌ Lỗi MySQL khi ghi nhật ký vào `access_log`: {err}")
    finally:
        cursor.close()
        conn.close()
def open_buzzer(thời_gian=1):
    GPIO.output(BUZZER, GPIO.HIGH)  # Bật buzzer
    time.sleep(thời_gian)           # Giữ buzzer trong khoảng thời gian nhất định
    GPIO.output(BUZZER, GPIO.LOW)    # Tắt buzzer

# Thiết lập các chân hàng là output
for row in ROW_PINS:
    GPIO.setup(row, GPIO.OUT)

# Thiết lập các chân cột là input với pull-down resistor
for col in COL_PINS:
    GPIO.setup(col, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
#xử lý password
#------------------- xử lý dữ liệu nhập từ matrix phím ---------------------
# Cập nhật mật khẩu mới vào cơ sở dữ liệu
def get_password(user_name):
    try:
        conn = connect_db()
        if conn is None:
            return None

        cursor = conn.cursor()
        cursor.execute("SELECT password FROM system_settings WHERE id = 1")  # Lấy mật khẩu gốc trực tiếp
        result = cursor.fetchone()

        cursor.close()
        conn.close()

        if result:
            password = result[0]  # Lấy mật khẩu gốc từ cơ sở dữ liệu
            print(f"✅ Đã lấy mật khẩu từ DB:\nPassword: {password}")
            return password  # Trả về mật khẩu
        else:
            print("❌ Không tìm thấy người dùng!")
            return None
    except mysql.connector.Error as err:
        print(f"❌ Lỗi khi lấy mật khẩu từ DB: {err}")
        return None


def update_password(user_name, new_password):
    try:
        conn = connect_db()
        if conn is None:
            return {"status": "error", "message": "Không thể kết nối đến cơ sở dữ liệu"}

        cursor = conn.cursor()
        # Cập nhật mật khẩu trực tiếp vào bảng `system_settings`
        cursor.execute("UPDATE system_settings SET password = %s, updated_at = NOW() WHERE id = 1", (new_password,))
        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "message": "Mật khẩu đã được cập nhật"}

    except mysql.connector.Error as err:
        print(f"❌ Lỗi khi cập nhật mật khẩu: {err}")
        return {"status": "error", "message": "Lỗi khi cập nhật mật khẩu"}



def SendEmail(sender, pass_sender, receiver):
    # Tạo email mới
    newMessage = EmailMessage()
    newMessage['Subject'] = "CANH BAO !!!"
    newMessage['From'] = sender
    newMessage['To'] = receiver
    newMessage.set_content('CANH BAO AN NINH')  # Nội dung email chỉ là cảnh báo

    # Gửi email
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()  # Bắt đầu mã hóa TLS
            smtp.login(sender, pass_sender)  # Đăng nhập vào email
            smtp.send_message(newMessage)  # Gửi email
            print(f"✅ Đã gửi email tới {receiver} với cảnh báo.")
    except Exception as e:
        print(f"❌ Lỗi khi gửi email: {e}")
#get dữ liệu từ bàn phím 
# Hàm kiểm tra dữ liệu đầu vào
def isBufferdata(data=[]):
    if len(data) < 5:
        return 0
    for i in range(5):
        if data[i] == '\0':
            return 0
    return 1

# Hàm ghi dữ liệu vào biến new_pass1 và new_pass2
def insertData(data1, data2):
    if len(data1) != len(data2):
        print("Lỗi: Kích thước của data1 và data2 không khớp.")
        return  # Thoát nếu kích thước không khớp
    for i in range(len(data1)):
        data1[i] = data2[i]  # Gán giá trị từ data2 vào data1

# Hàm so sánh hai danh sách dữ liệu
def compareData(data1=[], data2=[]):
    for i in range(5):
        if data1[i] != data2[i]:
            return False
    return True

# Hàm xóa dữ liệu đầu vào
def clear_data_input():
    global data_input
    data_input = []

# Hàm ghi mật khẩu mới vào EEPROM (giả lập)
def writeEpprom(new_pass):
    print(f"Ghi mật khẩu mới vào EEPROM: {new_pass}")
    # Thực hiện ghi vào EEPROM ở đây
def clear_lcd():
    lcd.clear()
    lcd.home()  # Ðua con tro ve vi trí ban d?u
    time.sleep(0.1)  


def reset_lcd_to_default():
    clear_lcd()  # Xóa nội dung trên LCD
    lcd.write_string("---CLOSEDOOR---")  # Hiển thị trạng thái mặc định "Cửa khóa"
# Hàm kiểm tra mật khẩu
def read_line(row):
    GPIO.output(row, GPIO.HIGH)  # Kích hoạt hàng hiện tại
    
    for i, col in enumerate(COL_PINS):
        if GPIO.input(col) == 1:
            key_pressed = KEYPAD[ROW_PINS.index(row)][i]  # Lấy ký tự tương ứng
            print(f"Key pressed: {key_pressed}")
            data_input.append(key_pressed)  # Thêm ký tự vào data_input
            
            # Xóa màn hình LCD trước khi cập nhật nội dung mới
            clear_lcd()
            
            # Hiển thị tiến trình nhập mật khẩu trên màn hình LCD
            lcd.write_string("Checking pass:")
            lcd.cursor_pos = (1, 0)  # Di chuyển con trỏ đến dòng thứ hai
            lcd.write_string('*' * len(data_input))  # Hiển thị dấu '*' cho mỗi ký tự được nhập
            
            time.sleep(0.3)  # Tạm dừng để tránh trùng lặp
    GPIO.output(row, GPIO.LOW)  # Tắt hàng hiện tại

# Hàm kiểm tra mật khẩu

def check_pass():
    global password_input, is_checking_password, Sender_email, pass_sender, Reciever_Email, is_yolo_active

    clear_lcd()
    lcd.write_string("Checking pass:")

    while True:
        if len(data_input) < 5:
            for row in ROW_PINS:
                read_line(row)
            time.sleep(0.1)
        else:
            is_checking_password = True
            password_input = ''.join(data_input)

            stored_password = get_password("user_name")
            if stored_password:
                print(f"✅ Nhập: {password_input}")
                print(f"✅ DB: {stored_password}")

                # Kiểm tra mật khẩu
                if password_input == stored_password:
                    lcd.clear()
                    lcd.write_string("ACCESS GRANTED")
                    GPIO.output(RELAY_PIN, GPIO.HIGH)
                    log_access("User", "Password", "Mở cửa bằng mật khẩu")
                    time.sleep(5)
                    GPIO.output(RELAY_PIN, GPIO.LOW)

                    is_yolo_active = False
                    time.sleep(10)
                    is_yolo_active = True

                # Chế độ thay đổi mật khẩu
                elif password_input == mode_changePass:
                    changePass()

                # Chế độ reset mật khẩu
                elif password_input == mode_resetPass:
                    resetPass()

                # Chế độ thêm thẻ RFID
                elif password_input == mode_addRFID:
                    add_new_rfid()

                # Chế độ xóa thẻ RFID
                # elif password_input == mode_delRFID:
                #     del_rfid()

                # # Chế độ xóa tất cả thẻ RFID
                # elif password_input == mode_delAllRFID:
                #     del_all_rfid()

                else:
                    lcd.clear()
                    lcd.write_string("WRONG PASSWORD")
                    open_buzzer(1)
                    print("❌ Sai mật khẩu!")
                    SendEmail(Sender_email, pass_sender, Reciever_Email)

            else:
                print("⚠ Không lấy được mật khẩu từ DB.")

            is_checking_password = False
            clear_data_input()
            time.sleep(2)
            reset_lcd_to_default()
  # Đặt lại trạng thái màn hình về mặc định  # Đặt lại trạng thái màn hình về mặc định
  # Đặt lại trạng thái màn hình về mặc định


def changePass():
    global password, new_pass1, new_pass2
    clear_lcd()  # Xóa màn hình ngay khi bắt đầu
    lcd.write_string('-- Change Pass --')
    print('--- Đổi mật khẩu ---')
    time.sleep(2)
    
    clear_data_input()

    clear_lcd()  # Chỉ xóa màn hình trước khi hiển thị nội dung mới
    lcd.write_string("--- New Pass ---")

    # Nhập mật khẩu mới lần 1
    while True:
        if len(data_input) < 5:
            for row in ROW_PINS:
                read_line(row)
            time.sleep(0.1)

            # Chỉ cập nhật dấu '*' khi có sự thay đổi trong data_input
            lcd.cursor_pos = (1, 0)
            lcd.write_string('*' * len(data_input))

        if isBufferdata(data_input):  # Khi đã nhập đủ dữ liệu
            insertData(new_pass1, data_input)
            clear_data_input()  # Xóa dữ liệu nhập lần 1
            lcd.clear()  # Xóa màn hình khi hoàn thành việc nhập
            lcd.write_string("--- PASSWORD ---")
            print("---- AGAIN ----")
            break

    # Nhập lại mật khẩu lần 2
    while True:
        if len(data_input) < 5:
            for row in ROW_PINS:
                read_line(row)
            time.sleep(0.1)

            # Hiển thị tiến trình nhập lại mật khẩu lần 2
            lcd.cursor_pos = (1, 0)
            lcd.write_string('*' * len(data_input))

        if isBufferdata(data_input):  # Khi đã nhập đủ lần 2
            insertData(new_pass2, data_input)
            break

    time.sleep(1)

    # So sánh hai lần nhập mật khẩu
    if compareData(new_pass1, new_pass2):
        lcd.clear()  # Chỉ xóa khi thực sự cần hiển thị nội dung khác
        lcd.write_string("--- Success ---")
        print("--- Mật khẩu khớp ---")
        time.sleep(1)
        writeEpprom(new_pass2)
        password = ''.join(new_pass2)

        # Ghi mật khẩu mới vào cơ sở dữ liệu
        update_password("user_name", password)

        # Ghi mật khẩu mới vào file password.txt
        try:
            with open('password.txt', 'w') as file:
                file.write(password)
            print("Mật khẩu mới đã được lưu vào file.")
        except IOError:
            print("Không thể ghi mật khẩu vào file.")

        # Ghi log khi thay đổi mật khẩu
        log_access("Admin", "Change Password", "Đổi mật khẩu thành công")

        lcd.clear()  # Xóa màn hình trước khi thông báo thành công
        lcd.write_string("Đổi MK thành công")
        time.sleep(2)

def resetPass():
    global password
    clear_lcd()  # Xóa LCD trước khi hiển thị nội dung mới
    lcd.write_string('--- Reset Pass ---')  # Hiển thị "Reset Pass" trên LCD
    print('--- Reset Pass ---')
    time.sleep(2)  # Cho phép người dùng nhìn thấy thông báo trên LCD

    clear_data_input()
    
    # Bắt đầu quá trình nhập mật khẩu hiện tại để xác nhận
    clear_lcd()  # Xóa LCD trước khi hiển thị nội dung mới
    lcd.write_string("--- PassWord ---")

    while True:
        if len(data_input) < 5:  # Giả sử mật khẩu có 5 ký tự
            for row in ROW_PINS:
                read_line(row)  # Gọi hàm để đọc ký tự từ bàn phím ma trận
            time.sleep(0.1)  # Tạm dừng một chút để tránh việc lặp quá nhanh

            # Hiển thị tiến trình nhập mật khẩu hiện tại
            clear_lcd()  # Xóa màn hình trước khi cập nhật
            lcd.write_string("R1enter password")
            lcd.cursor_pos = (1, 0)  # Di chuyển con trỏ đến dòng thứ hai
            lcd.write_string('*' * len(data_input))  # Hiển thị dấu '*' đại diện cho ký tự đã nhập

        if isBufferdata(data_input):  # Kiểm tra xem người dùng đã nhập đủ 5 ký tự
            if compareData(data_input, password):  # So sánh với mật khẩu hiện tại
                clear_data_input()  # Xóa dữ liệu nhập sau khi xác nhận thành công
                clear_lcd()  # Xóa màn hình trước khi thông báo thành công
                lcd.write_string('---resetting...---')
                print('Mật khẩu đúng, sẵn sàng reset!')
                
                # Đợi 2 giây để thông báo thành công trước khi tiếp tục
                time.sleep(2)

                while True:
                    key = None  # Đặt mặc định key là None để kiểm tra
                    for row in ROW_PINS:
                        GPIO.output(row, GPIO.HIGH)
                        for i, col in enumerate(COL_PINS):
                            if GPIO.input(col) == 1:
                                key = KEYPAD[ROW_PINS.index(row)][i]
                                time.sleep(0.3)  # Tránh trùng lặp khi nhấn
                        GPIO.output(row, GPIO.LOW)

                    if key == '#':  # Khi người dùng nhấn phím '#'
                        new_default_pass = list(pass_def)  # Mật khẩu mặc định thành danh sách
                        new_password = list(password)  # Chuyển đổi mật khẩu hiện tại thành danh sách
                        insertData(new_password, new_default_pass)  # Đặt lại mật khẩu mặc định
                        clear_lcd()  # Xóa LCD trước khi hiển thị thông báo mới
                        lcd.write_string('---reset successful---')
                        print('--- Reset mật khẩu thành công ---')
                        writeEpprom(pass_def)  # Giả lập ghi vào EEPROM
                        password = ''.join(new_password)  # Chuyển đổi danh sách trở lại chuỗi

                        # Ghi mật khẩu mới vào file password.txt
                        try:
                            with open('password.txt', 'w') as file:
                                file.write(password)
                            print("Mật khẩu mới đã được lưu vào file.")
                        except IOError:
                            print("Không thể ghi mật khẩu vào file.")

                        clear_data_input()  # Xóa dữ liệu nhập
                        time.sleep(2)  # Hiển thị thông báo thành công trong 2 giây
                        clear_lcd()  # Xóa màn hình sau khi thông báo thành công
                        return  # Thoát hàm reset sau khi hoàn thành
            else:
                # Xử lý khi mật khẩu hiện tại không đúng
                clear_lcd()  # Xóa màn hình trước khi thông báo lỗi
                lcd.write_string('---ERROR---')
                print('Mật khẩu không đúng!')
                
                # Gửi email cảnh báo
                SendEmail(Sender_email, pass_sender, Reciever_Email)

                clear_data_input()  # Xóa dữ liệu nhập khi sai mật khẩu
                time.sleep(2)  # Hiển thị thông báo trong 2 giây
                clear_lcd()  # Xóa màn hình sau khi thông báo sai mật khẩu
                break  # Kết thúc nếu mật khẩu nhập sai  # Kết thúc nếu mật khẩu nhập sai

#-----------------------------------------------------------

# Hàm điều khiển servo

# Hàm bật/tắt đèn
def turn_on_light():
    GPIO.output(light_pin, GPIO.HIGH)  # Bật đèn

def turn_off_light():
    GPIO.output(light_pin, GPIO.LOW)  # Tắt đèn

# Hàm lưu ảnh khi phát hiện xâm nhập
def save_image(frame):
    # Lưu ảnh vào thư mục 'intrusions'
    save_dir = "/home/admin/Desktop/YOLO/YOLO/intrusions"
    os.makedirs(save_dir, exist_ok=True)

    now = datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S_%f')[:-3]  # Định dạng tên tệp theo thời gian

    filename = os.path.join(save_dir, f"alert_INTRUSION_{timestamp}.jpg")
    
    # Lưu ảnh
    cv2.imwrite(filename, frame)
    print(f"[💾] Ảnh xâm nhập đã lưu: {filename}")



# Hàm điều khiển servo
def move_servo(pin, angle):
    # """
    # Điều khiển servo thông qua pigpio
    # - pin: GPIO số (17 hoặc 18)
    # - angle: góc cần quay (0–180 độ)
    # """

    angle = max(0, min(180, angle))  # Giới hạn trong khoảng an toàn
    pulsewidth = int(500 + (angle / 180.0) * 2000)  # Chuyển góc sang microseconds (500–2500µs)

    pi.set_servo_pulsewidth(pin, pulsewidth)  # Gửi lệnh quay servo
    print(f"[⚙️] Servo GPIO{pin} quay đến: {angle:.1f}° → {pulsewidth} µs")

    time.sleep(0.3)  # Cho phép servo có thời gian quay

    # (Tuỳ chọn) Tắt tín hiệu PWM để servo không rung sau khi quay xong
    pi.set_servo_pulsewidth(pin, 0)




# Hàm điều khiển servo trong một luồng riêng
# Thay thế hàm move_servo_thread để sử dụng ThreadPoolExecutor
def servo_worker():
    while True:
        task = servo_queue.get()
        if task is None:
            break
        try:
            if isinstance(task, tuple) and len(task) == 2:
                action, args = task
                if callable(action):
                    action(*args)
                else:
                    print("❌ Lỗi: action không phải callable")
            else:
                print("❌ Lỗi: task không đúng định dạng (action, args)")
        except Exception as e:
            print("❌ Lỗi servo task:", e)
        finally:
            servo_queue.task_done()


def follow_person_and_alert(cx, cy, frame_width, frame_height, frame):
    servo_1_angle = (cx / frame_width) * 180
    servo_2_angle = (cy / frame_height) * 180

    servo_queue.put((move_servo, (servo_pin_1, servo_1_angle)))
    servo_queue.put((move_servo, (servo_pin_2, servo_2_angle)))
    servo_queue.put((turn_on_light, ()))
    servo_queue.put((save_image, (frame.copy(),)))  # copy để tránh bị thay đổi

    def delayed_light_off():
        time.sleep(5)
        servo_queue.put((turn_off_light, ()))

    threading.Thread(target=delayed_light_off, daemon=True).start()


# === Hàm phát hiện người và xử lý ===
def detect_person_and_alert(frame):
    small_frame = cv2.resize(frame, (416, 416))
    height, width = small_frame.shape[:2]

    blob = cv2.dnn.blobFromImage(small_frame, 1/255.0, (416, 416), swapRB=True, crop=False)
    model.model.setInput(blob)

    layer_names = model.model.getLayerNames()
    output_layers = [layer_names[i - 1] for i in model.model.getUnconnectedOutLayers()]
    outputs = model.model.forward(output_layers)

    detections = []
    for output in outputs:
        for detection in output:
            scores = detection[5:]
            class_id = int(np.argmax(scores))
            confidence = scores[class_id]
            if class_id == 0 and confidence > 0.5:
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                detections.append({
                    "label": "person",
                    "box": [x, y, w, h],
                    "center": (center_x, center_y)
                })

    h_ratio = frame.shape[0] / 416
    w_ratio = frame.shape[1] / 416

    for obj in detections:
        x, y, w, h = obj['box']
        x = int(x * w_ratio)
        y = int(y * h_ratio)
        w = int(w * w_ratio)
        h = int(h * h_ratio)
        cx, cy = x + w // 2, y + h // 2

        # Khi phát hiện người, di chuyển servo và bật đèn
        follow_person_and_alert(cx, cy, frame.shape[1], frame.shape[0], frame)


behavior_model = joblib.load("models/behavior_model.pkl")

# Khởi tạo bộ nhớ lưu tọa độ cũ để tính tốc độ
person_last_pos = {}

# === Flask App Khởi Tạo ===
app = Flask(__name__)

# === Camera & Model ===
picam2 = Picamera2()
preview_config = picam2.create_preview_configuration(main={"size": (640, 480)})
picam2.configure(preview_config)
picam2.start()
time.sleep(1)
model = YoloDetect()

# === Biến toàn cục dùng chung ===
latest_frame = None
frame_lock = threading.Lock()
points = []
detect = False
person_position = None
person_position_lock = threading.Lock()

class PersonTracker:
    def __init__(self):
        self.people = {}  # id: {bbox, start_time, last_seen}

    def update(self, person_id, bbox):
        now = time.time()
        if person_id in self.people:
            self.people[person_id]["last_seen"] = now
            self.people[person_id]["bbox"] = bbox
        else:
            self.people[person_id] = {"start_time": now, "last_seen": now, "bbox": bbox}

    def get_standing_too_long(self, timeout=10):
        now = time.time()
        result = []
        for pid, data in self.people.items():
            duration = data["last_seen"] - data["start_time"]
            if duration >= timeout:
                result.append((pid, duration, data["bbox"]))
        return result

def point_to_polygon_distance(point, polygon_points):
    if len(polygon_points) < 3:
        return float('inf')  # chưa đủ định nghĩa 1 vùng
    p = Point(point)
    poly = Polygon(polygon_points)
    return p.distance(poly)

# === Hàm Stream MJPEG ===
def generate():
    while True:
        with frame_lock:
            if latest_frame is None:
                continue
            ret, jpeg = cv2.imencode('.jpg', latest_frame)
            if not ret:
                continue
            frame = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# === Flask Route: Trang chính (HTML) ===
@app.route('/')
def index():
    return '''
    <html>
        <head>
            <title>🔴 Camera Stream</title>
            <style>
                body { background-color: black; text-align: center; margin: 0; }
                img { width: 100vw; height: auto; max-width: 100%; }
            </style>
        </head>
        <body>
            <img src="/video_feed" />
        </body>
    </html>
    '''

# === Flask Route: Trả về MJPEG stream ===
@app.route('/video_feed')
def video_feed():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

# === Hàm vẽ đa giác vùng cấm ===
def draw_polygon(frame, points):
    for point in points:
        frame = cv2.circle(frame, tuple(point), 5, (0, 0, 255), -1)
    if len(points) > 1:
        frame = cv2.polylines(frame, [np.int32(points)], isClosed=True, color=(255, 0, 0), thickness=2)
    return frame

def point_in_polygon(point, polygon):
    if len(polygon) < 3:
        return False
    return cv2.pointPolygonTest(np.array(polygon, dtype=np.int32), point, False) >= 0

# === Hàm bắt chuột trái để tạo vùng cấm ===
def handle_left_click(event, x, y, flags, param):
    global points
    if event == cv2.EVENT_LBUTTONDOWN and not detect:
        points.append([x, y])


def move_both_servos(angle1, angle2):
    angle1 = max(0, min(180, angle1))
    angle2 = max(0, min(180, angle2))

    pw1 = int(500 + (angle1 / 180.0) * 2000)
    pw2 = int(500 + (angle2 / 180.0) * 2000)

    pi.set_servo_pulsewidth(servo_pin_1, pw1)
    pi.set_servo_pulsewidth(servo_pin_2, pw2)

    time.sleep(0.3)

    pi.set_servo_pulsewidth(servo_pin_1, 0)
    pi.set_servo_pulsewidth(servo_pin_2, 0)
def read_auto_mode():
    try:
        with open("/home/pi/auto_mode.txt", "r") as f:
            return f.read().strip() == "on"
    except:
        return True


def servo_tracking_loop():
    global current_angle_1, current_angle_2

    last_angles = [None, None]  # Lưu góc cũ cho servo 1 và 2

    while True:
        time.sleep(0.2)  # cập nhật mỗi 200ms

        # 🔄 Lấy trạng thái từ PHP
        state = get_device_state()
        auto_mode = state.get("auto", "on") == "on"

        if not auto_mode:
            continue  # nếu chế độ TAY thì bỏ qua xoay

        with person_position_lock:
            if person_position is None:
                continue
            cx, cy, w, h = person_position

        angle1 = (cx / w) * 180
        angle2 = (cy / h) * 180

        # CHỈ gửi nếu có thay đổi đáng kể
        should_update = (
            last_angles[0] is None or abs(angle1 - last_angles[0]) > 3 or
            last_angles[1] is None or abs(angle2 - last_angles[1]) > 3
        )

        if should_update:
            last_angles = [angle1, angle2]
            current_angle_1 = angle1
            current_angle_2 = angle2
            servo_queue.put((move_both_servos, (angle1, angle2)))



# === Luồng xử lý camera và hiển thị ===
def camera_loop():
    global latest_frame, detect,is_yolo_active

    mp_pose = mp.solutions.pose
    pose_detector = mp_pose.Pose(static_image_mode=False, model_complexity=0, enable_segmentation=False)

    behavior_model = joblib.load("models/behavior_model.pkl")  # ✅ AI model
    person_last_pos = {}

    fps_counter = 0
    fps_display = 0
    fps_timer = time.time()
    frame_count = 0

    tracker = PersonTracker()

    cv2.namedWindow("Intrusion Warning")
    cv2.setMouseCallback("Intrusion Warning", handle_left_click)

    while True:
        try:
            frame = picam2.capture_array()
            frame = cv2.resize(frame, (640, 480))
            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            frame = cv2.flip(frame, 1)

            frame = draw_polygon(frame, points)

            if detect and len(points) > 2 and frame_count % 2 == 0:
                if is_yolo_active:
                    small_frame = cv2.resize(frame, (416, 416))
                    height, width = small_frame.shape[:2]

                    blob = cv2.dnn.blobFromImage(small_frame, 1/255.0, (416, 416), swapRB=True, crop=False)
                    model.model.setInput(blob)

                    layer_names = model.model.getLayerNames()
                    output_layers = [layer_names[i - 1] for i in model.model.getUnconnectedOutLayers()]
                    outputs = model.model.forward(output_layers)

                    detections = []
                    for output in outputs:
                        for detection in output:
                            scores = detection[5:]
                            class_id = int(np.argmax(scores))
                            confidence = scores[class_id]
                            if class_id == 0 and confidence > 0.5:
                                center_x = int(detection[0] * width)
                                center_y = int(detection[1] * height)
                                w = int(detection[2] * width)
                                h = int(detection[3] * height)
                                x = int(center_x - w / 2)
                                y = int(center_y - h / 2)
                                detections.append({
                                    "label": "person",
                                    "box": [x, y, w, h],
                                    "center": (center_x, center_y)
                                })

                    h_ratio = frame.shape[0] / 416
                    w_ratio = frame.shape[1] / 416

                    for obj in detections:
                        x, y, w, h = obj['box']
                        x = int(x * w_ratio)
                        y = int(y * h_ratio)
                        w = int(w * w_ratio)
                        h = int(h * h_ratio)
                        cx, cy = x + w // 2, y + h // 2
                        with person_position_lock:
                            person_position = (cx, cy, frame.shape[1], frame.shape[0])
                        person_id = hash(f"{x//10}-{y//10}")
                        tracker.update(person_id, (x, y, w, h))

                        # Kiểm tra xem người có vào vùng cấm không
                        if point_in_polygon((cx, cy), points):  # Kiểm tra nếu người vào vùng cấm
                            follow_person_and_alert(cx, cy, frame.shape[1], frame.shape[0], frame)
                            cv2.putText(frame, "🚨 XÂM NHẬP!", (x, y - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                            print(f"[🚨] Phát hiện xâm nhập tại ({x}, {y})")
                            model.alert(frame.copy(), alert_type="INTRUSION")

                            # === CHỤP ẢNH NGƯỜI XÂM NHẬP ===
                            save_dir = "/var/www/html/uploads"
                            os.makedirs(save_dir, exist_ok=True)

                            now = datetime.now()
                            timestamp = now.strftime('%Y%m%d_%H%M%S_%f')[:-3]

                            filename = os.path.join(save_dir, f"alert_INTRUSION_{timestamp}.jpg")

                            # Cắt phần người xâm nhập ra khỏi khung hình
                            person_crop = frame[y:y+h, x:x+w]
                            if person_crop.size > 0:
                                cv2.imwrite(filename, person_crop)
                                print(f"[🕒] Giờ lưu ảnh: {now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
                                print(f"[💾] Ảnh xâm nhập đã lưu: {filename}")

                            person_crop = frame[y:y+h, x:x+w]
                            if person_crop.size > 0:
                                cv2.imwrite(filename, person_crop)
                                print(f"[💾] Ảnh xâm nhập đã lưu: {filename}")

                            # === Điều khiển Servo và bật đèn khi phát hiện người ===
                            follow_person_and_alert(cx, cy, frame.shape[1], frame.shape[0], frame)

                        distance = point_to_polygon_distance((cx, cy), points)
                        prev = person_last_pos.get(person_id)
                        speed = 0
                        if prev:
                            dx = abs(cx - prev[0])
                            dy = abs(cy - prev[1])
                            speed = (dx + dy) / 2
                        person_last_pos[person_id] = (cx, cy)
                        duration = time.time() - tracker.people[person_id]["start_time"]

                        try:
                            features = [[distance, w, h, speed, duration]]
                            pred = behavior_model.predict(features)[0]
                            if pred == 1:
                                cv2.putText(frame, "AI 🚨 XÂM NHẬP", (x, y + h + 20),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                                print(f"[AI 🚨] Dự đoán: XÂM NHẬP tại ({x}, {y})")
                                model.alert(frame.copy(), alert_type="INTRUSION_AI")
                            elif pred == 2:
                                cv2.putText(frame, "AI 🤨 NGHI NGỜ", (x, y + h + 20),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
                                print(f"[AI 🤨] Dự đoán: HÀNH VI NGHI NGỜ tại ({x}, {y})")
                                model.alert(frame.copy(), alert_type="SUSPICIOUS_AI")
                        except Exception as e:
                            print("[AI ERROR]", e)

                        behavior = "?"
                        if w > 80 and h > 120:
                            person_img = frame[y:y+h, x:x+w]
                            if person_img.size > 0:
                                rgb_person = cv2.cvtColor(person_img, cv2.COLOR_BGR2RGB)
                                result = pose_detector.process(rgb_person)
                                if result.pose_landmarks:
                                    try:
                                        landmarks = result.pose_landmarks.landmark
                                        a = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
                                        b = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
                                        c = landmarks[mp_pose.PoseLandmark.LEFT_KNEE]

                                        def get_angle(a, b, c):
                                            ang = math.degrees(math.atan2(c.y - b.y, c.x - b.x) - 
                                                            math.atan2(a.y - b.y, a.x - b.x))
                                            return abs(ang if ang <= 180 else 360 - ang)

                                        angle = get_angle(a, b, c)
                                        if angle > 140:
                                            behavior = "ĐỨNG"
                                        elif angle > 90:
                                            behavior = "NGỒI"
                                        else:
                                            behavior = "NẰM / NGÃ?"
                                    except:
                                        behavior = "KHÔNG XÁC ĐỊNH"

                        # 🚨 Xác định ngã
                        if behavior == "NẰM / NGÃ?":
                            now = time.time()
                            last = tracker.people[person_id].get("last_alert", 0)
                            is_laying_orientation = w > h * 1.3
                            is_low_movement = speed < 2

                            if is_laying_orientation and is_low_movement and now - last > 5:
                                tracker.people[person_id]["last_alert"] = now
                                behavior = "TÉ NGÃ"
                                cv2.putText(frame, "⚠️ XÁC NHẬN NGÃ", (x, y + h + 40),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                                print(f"[✅] Phát hiện NGÃ tại ({x}, {y})")
                                model.alert(frame.copy(), alert_type="FALL_CONFIRMED")
                            else:
                                cv2.putText(frame, "⚠️ NGHI TÉ NGÃ", (x, y + h + 40),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                                print(f"[❗] Người có dấu hiệu ngã (chưa xác nhận) tại ({x}, {y})")

                        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 0), 2)
                        cv2.putText(frame, f"{behavior}", (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                    (0, 255, 255) if behavior == "TÉ NGÃ" else (255, 255, 0), 2)

                    warnings = tracker.get_standing_too_long(timeout=10)
                    for pid, duration, bbox in warnings:
                        x, y, w, h = bbox
                        cv2.putText(frame, f"⏱ {duration:.1f}s", (x, y + h + 60),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        print(f"[⚠️] Người ID {pid} đứng quá lâu ({duration:.1f}s) tại {bbox}")

            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                fps_display = fps_counter
                fps_counter = 0
                fps_timer = time.time()

            cv2.putText(frame, f"FPS: {fps_display}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            with frame_lock:
                latest_frame = frame.copy()

            cv2.imshow("Intrusion Warning", frame)
            key = cv2.waitKey(1)
            if key == ord('q'):
                break
            elif key == ord('r'):
                points.clear()
                detect = False
            elif key == ord('d') and len(points) > 2:
                points.append(points[0])
                detect = True

            frame_count += 1

        except Exception as e:
            print("❌ Lỗi camera loop:", e)
            break

    picam2.stop()
    cv2.destroyAllWindows()


# === Run Camera Loop và Web Flask song song ===
if __name__ == '__main__':
    @app.route('/control_servo/<cmd>')
    def control_servo(cmd):
        global auto_mode, current_angle_1, current_angle_2

        if auto_mode:
            return {"status": "error", "message": "Đang ở chế độ TỰ ĐỘNG"}

        step = 5  # góc xoay mỗi lần nhấn
        if cmd == "up":
            current_angle_2 = max(0, current_angle_2 - step)
        elif cmd == "down":
            current_angle_2 = min(180, current_angle_2 + step)
        elif cmd == "left":
            current_angle_1 = max(0, current_angle_1 - step)
        elif cmd == "right":
            current_angle_1 = min(180, current_angle_1 + step)
        else:
            return {"status": "error", "message": "Lệnh không hợp lệ"}

        # Gửi lệnh di chuyển đến góc hiện tại
        servo_queue.put((move_both_servos, (current_angle_1, current_angle_2)))

        return {"status": "success", "message": f"Servo moved: {cmd}", "angle1": current_angle_1, "angle2": current_angle_2}
    
    
    # Khởi tạo và chạy luồng RFID
    rfid_thread = threading.Thread(target=run_rfid_thread)
    rfid_thread.daemon = True  # Đảm bảo luồng này sẽ kết thúc khi chương trình chính kết thúc
    rfid_thread.start()

    password_thread = threading.Thread(target=check_pass)
    password_thread.start()
    # Khởi động luồng xử lý servo queue
    servo_thread = threading.Thread(target=servo_worker, daemon=True)
    servo_thread.start()

    # Khởi động luồng tracking người (xoay servo theo người mới nhất)
    tracking_thread = threading.Thread(target=servo_tracking_loop, daemon=True)
    tracking_thread.start()

    # Khởi động camera loop song song
    camera_thread = threading.Thread(target=camera_loop, daemon=True)
    camera_thread.start()

    # Khởi động server Flask
    app.run(host='0.0.0.0', port=5000, debug=False)

    # Khi Flask server kết thúc (thường là khi bấm Ctrl+C)
    servo_queue.put(None)     # gửi tín hiệu dừng cho servo_worker
    servo_thread.join()

