import pigpio
import time

pi = pigpio.pi()

servo_pin = 17  # hoặc 18

for angle in range(0, 181, 30):
    pw = int(500 + (angle / 180.0) * 2000)
    pi.set_servo_pulsewidth(servo_pin, pw)
    print(f"Quay {angle}° → {pw}µs")
    time.sleep(1)

pi.set_servo_pulsewidth(servo_pin, 0)
