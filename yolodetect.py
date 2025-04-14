from shapely.geometry import Point, Polygon
import cv2
import numpy as np
from telegram_utils import send_telegram
import datetime
import asyncio
import threading
import os

def send_telegram_thread(photo_path):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(send_telegram(photo_path))
    except Exception as e:
        print("❌ Không gửi được cảnh báo:", e)
    finally:
        loop.close()

def isInside(points, centroid):
    polygon = Polygon(points)
    centroid = Point(centroid)
    inside = polygon.contains(centroid)
    print(f"[CHECK] Centroid {centroid} in region? {inside}")
    return inside

class YoloDetect():
    def __init__(self, detect_class="person", frame_width=1280, frame_height=720):
        self.classnames_file = "model/coco.names"
        self.weights_file = "model/yolov4-tiny.weights"
        self.config_file = "model/yolov4-tiny.cfg"
        self.conf_threshold = 0.5
        self.nms_threshold = 0.4
        self.detect_class = detect_class
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.scale = 1 / 255.0
        self.model = cv2.dnn.readNet(self.weights_file, self.config_file)
        self.classes = []
        self.output_layers = []
        self.read_class_file()
        self.get_output_layers()
        self.last_alert = None
        self.alert_telegram_each = 15  # seconds

        os.makedirs("alerts", exist_ok=True)

    def read_class_file(self):
        with open(self.classnames_file, 'r') as f:
            self.classes = [line.strip() for line in f.readlines()]

    def get_output_layers(self):
        layer_names = self.model.getLayerNames()
        self.output_layers = [layer_names[i - 1] for i in self.model.getUnconnectedOutLayers().flatten()]

    def alert(self, img, alert_type="INTRUSION"):
        label = {
            "INTRUSION": "🚫 XÂM NHẬP",
            "FALL": "⚠️ TÉ NGÃ",
            "SUSPICIOUS": "🤨 HÀNH VI NGHI NGỜ"
        }.get(alert_type, "🚨 CẢNH BÁO")

        cv2.putText(img, label, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        now = datetime.datetime.now()  # Lấy giờ hệ thống (đã đúng GMT+7)
        if (self.last_alert is None) or ((now - self.last_alert).total_seconds() > self.alert_telegram_each):
            self.last_alert = now
            timestamp = now.strftime("%Y%m%d_%H%M%S")
            os.makedirs("intrusions", exist_ok=True)
            alert_path = f"intrusions/alert_{alert_type}_{timestamp}.jpg"
            cv2.imwrite(alert_path, cv2.resize(img, dsize=None, fx=0.5, fy=0.5))
            try:
                threading.Thread(target=send_telegram_thread, args=(alert_path,), daemon=True).start()
                print(f"[ALERT SENT] Gửi ảnh {alert_type} thành công.")
            except Exception as e:
                print("[ERROR] Không gửi được cảnh báo:", e)
        return img

    def draw_prediction(self, img, class_id, x, y, x_plus_w, y_plus_h, points):
        label = str(self.classes[class_id])
        color = (0, 255, 0)
        cv2.rectangle(img, (x, y), (x_plus_w, y_plus_h), color, 2)
        cv2.putText(img, label, (x - 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        centroid = ((x + x_plus_w) // 2, (y + y_plus_h) // 2)
        cv2.circle(img, centroid, 5, color, -1)

        if isInside(points, centroid):
            img = self.alert(img, alert_type="INTRUSION")

        return img

    def detect(self, frame, points):
        blob = cv2.dnn.blobFromImage(frame, self.scale, (416, 416), (0, 0, 0), swapRB=True, crop=False)
        self.model.setInput(blob)
        outs = self.model.forward(self.output_layers)

        class_ids = []
        confidences = []
        boxes = []

        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]

                if confidence >= self.conf_threshold and self.classes[class_id] == self.detect_class:
                    center_x = int(detection[0] * self.frame_width)
                    center_y = int(detection[1] * self.frame_height)
                    w = int(detection[2] * self.frame_width)
                    h = int(detection[3] * self.frame_height)
                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)
                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))
                    class_ids.append(class_id)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, self.conf_threshold, self.nms_threshold)

        if len(indices) > 0:
            for i in indices:
                idx = i[0] if isinstance(i, (list, tuple, np.ndarray)) else i
                x, y, w, h = boxes[idx]
                self.draw_prediction(frame, class_ids[idx], x, y, x + w, y + h, points)

        return frame
