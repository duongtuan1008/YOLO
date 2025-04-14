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

# === Luồng xử lý camera và hiển thị ===
def camera_loop():
    global latest_frame, detect

    import mediapipe as mp
    import math
    import joblib
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

                    person_id = hash(f"{x//10}-{y//10}")
                    tracker.update(person_id, (x, y, w, h))

                    # Kiểm tra xem người có vào vùng cấm không
                    if point_in_polygon((cx, cy), points):  # Kiểm tra nếu người vào vùng cấm
                        cv2.putText(frame, "🚨 XÂM NHẬP!", (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        print(f"[🚨] Phát hiện xâm nhập tại ({x}, {y})")
                        model.alert(frame.copy(), alert_type="INTRUSION")

                        # === CHỤP ẢNH NGƯỜI XÂM NHẬP ===
                        save_dir = "/home/admin/Desktop/YOLO/YOLO"
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
    camera_thread = threading.Thread(target=camera_loop)
    camera_thread.daemon = True
    camera_thread.start()

    app.run(host='0.0.0.0', port=5000, debug=False)
