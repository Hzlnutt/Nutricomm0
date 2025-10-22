import paho.mqtt.client as mqtt
import json
import time
from threading import Thread
from pymongo import MongoClient
from app import socketio

# --- Koneksi MongoDB ---
mongo_client = MongoClient("mongodb://localhost:27017/")
db = mongo_client["iot_db"]
collection = db["sensor_data"]

# --- Konfigurasi MQTT ---
MQTT_BROKER = "192.168.0.182"
MQTT_PORT = 1883

def on_connect(client, userdata, flags, rc):
    print("✅ MQTT connected with result code", rc)
    # Langsung subscribe ke dua topik
    client.subscribe("iot/monitoring")
    client.subscribe("iot/lamp/status")
    print("📡 Subscribed to: iot/monitoring & iot/lamp/status")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"📩 Data diterima dari {msg.topic}: {payload}")

        # Simpan ke MongoDB
        collection.insert_one({
            "topic": msg.topic,
            "payload": payload,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        # Kirim ke frontend via SocketIO
        socketio.emit("sensor_update", payload)

        print("✅ Data tersimpan di database")

    except Exception as e:
        print("❌ Error parsing message:", e)

def start_mqtt(app, socketio):
    def mqtt_thread():
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()

    # Jalankan MQTT di thread terpisah supaya Flask tetap berjalan
    thread = Thread(target=mqtt_thread)
    thread.daemon = True
    thread.start()
