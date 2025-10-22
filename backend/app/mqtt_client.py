import json
import time
from threading import Thread
import paho.mqtt.client as mqtt


def _normalize_sensor_payload(raw: dict) -> dict:
    """Ubah payload dari berbagai format lama menjadi skema Nutricomm.

    Skema target:
    {
      "id_kebun": str,
      "suhu": float,
      "kelembapan_udara": float,
      "kelembapan_tanah": float,
      "cahaya": float,
      "co2": float,
      "timestamp": str (ISO8601)
    }

    Catatan: beberapa payload lama memakai key: temperature, humidity, gas.CO2, ldr
    """
    if raw is None:
        return {}

    # Ambil id_kebun jika ada; fallback "KBG001" (bisa disesuaikan di device)
    id_kebun = raw.get("id_kebun")
    if id_kebun is None:
        id_kebun = "KBG001"
    else:
        id_kebun = str(id_kebun)

    # Mapping nilai inti
    suhu = raw.get("suhu", raw.get("temperature"))
    kelembapan_udara = raw.get("kelembapan_udara", raw.get("humidity"))
    kelembapan_tanah = raw.get("kelembapan_tanah")

    # Cahaya bisa datang dari "cahaya" atau "ldr"
    cahaya = raw.get("cahaya", raw.get("ldr"))

    # CO2 bisa datang dari langsung "co2" atau nested di gas
    co2 = raw.get("co2")
    if co2 is None:
        gas = raw.get("gas") or {}
        if isinstance(gas, dict):
            co2 = gas.get("CO2") or gas.get("co2")

    # Timestamp: pakai yang dikirim device atau generate di server
    timestamp = raw.get("timestamp")
    if not timestamp:
        # ISO8601 sederhana
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    normalized = {
        "id_kebun": id_kebun,
        "suhu": suhu,
        "kelembapan_udara": kelembapan_udara,
        "kelembapan_tanah": kelembapan_tanah,
        "cahaya": cahaya,
        "co2": co2,
        "timestamp": timestamp,
    }

    # Buang key None supaya konsisten di DB
    return {k: v for k, v in normalized.items() if v is not None}


def start_mqtt(app, socketio):
    """Mulai client MQTT di thread terpisah, simpan data ke DB app, dan emit via SocketIO."""

    def mqtt_thread():
        # Ambil konfigurasi dari Flask app
        mqtt_host = app.config.get("MQTT_HOST", "localhost")
        mqtt_port = int(app.config.get("MQTT_PORT", 1883))

        db = app.db
        collection = db["sensor_data"]

        def on_connect(client, userdata, flags, rc):
            print("✅ MQTT connected with result code", rc)
            client.subscribe("iot/monitoring")
            print("📡 Subscribed to: iot/monitoring")

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
                print(f"📩 Data diterima dari {msg.topic}: {payload}")

                normalized = _normalize_sensor_payload(payload)
                if msg.topic == "iot/monitoring":
                    collection.insert_one(normalized)
                    socketio.emit("sensor_update", normalized, namespace="/ws")
                    print("✅ Data tersimpan & dikirim ke WebSocket")

            except Exception as e:
                print("❌ Error parsing message:", e)

        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(mqtt_host, mqtt_port, 60)
        client.loop_forever()

    thread = Thread(target=mqtt_thread)
    thread.daemon = True
    thread.start()
