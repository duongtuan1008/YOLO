import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib
import os

# Bước 1: Đọc dữ liệu
df = pd.read_csv("logs/behavior_log.csv", header=None,
                 names=["id", "cx", "cy", "w", "h", "distance", "behavior", "time", "speed", "duration"])

# Bước 2: Gán nhãn
# 👉 Gán nhãn dựa trên khoảng cách (distance):
# 0: bình thường, 1: xâm nhập gần, 2: nghi ngờ
def label_func(d):
    if d < 30:
        return 1  # xâm nhập
    elif d < 60:
        return 2  # nghi ngờ
    else:
        return 0  # bình thường

df["label"] = df["distance"].apply(label_func)

# Bước 3: Lấy đặc trưng và nhãn để huấn luyện
X = df[["distance", "w", "h", "speed", "duration"]]  # 5 đặc trưng
y = df["label"]

# Bước 4: Huấn luyện model
model = RandomForestClassifier()
model.fit(X, y)

# Bước 5: Lưu model
os.makedirs("models", exist_ok=True)
joblib.dump(model, "models/behavior_model.pkl")

print("✅ Mô hình đã được lưu vào models/behavior_model.pkl")
