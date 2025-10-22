from machine import Pin, ADC
import network, time, json, dht, urequests
from umqtt.simple import MQTTClient

# --- Pin Definisi ---
LAMP1 = Pin(5, Pin.OUT)
LAMP2 = Pin(18, Pin.OUT)
LAMP3 = Pin(19, Pin.OUT)
LAMP4 = Pin(21, Pin.OUT)
FAN = Pin(16, Pin.OUT)
BUZZER = Pin(23, Pin.OUT)

DHT11_PIN = Pin(15, Pin.IN)
MQ135_PIN = ADC(Pin(34))
LDR_PIN = ADC(Pin(32))

# --- ADC Setup ---
for adc in [MQ135_PIN, LDR_PIN]:
    adc.atten(ADC.ATTN_11DB)
    adc.width(ADC.WIDTH_12BIT)

dht11 = dht.DHT11(DHT11_PIN)

# --- WiFi & MQTT ---
SSID = "hotspotkeren"
PASSWORD = "87654321"
MQTT_SERVER = "192.168.137.1"  # IP broker (Laptop)
CLIENT_ID = "ESP32Client"
SERVER_IP = "192.168.0.182"    # IP Flask (Laptop)
url = f"http://{SERVER_IP}:5000/api/sensor"

# --- Variabel Global ---
lampStatus = [0, 0, 0, 0, 0]  # 4 lampu + kipas
fan_auto = True
client = None

# --- Koneksi WiFi ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("🔌 Menghubungkan WiFi...")
        wlan.connect(SSID, PASSWORD)
        while not wlan.isconnected():
            print(".", end="")
            time.sleep(0.5)
    print("\n✅ WiFi Terkoneksi:", wlan.ifconfig())

# --- MQTT Callback ---
def sub_cb(topic, msg):
    global fan_auto
    try:
        data = json.loads(msg.decode())
        lamp = int(data.get("lamp", 0))
        status = data.get("status", "")
        mode = data.get("mode", "")

        if lamp == 5:
            # mode kipas (AUTO/MANUAL)
            fan_auto = (mode == "AUTO")
            print(f"🌀 Kipas mode: {mode}")
            return

        if 1 <= lamp <= 5:
            idx = lamp - 1
            lampStatus[idx] = 1 if status == "ON" else 0
            relay = [LAMP1, LAMP2, LAMP3, LAMP4, FAN][idx]

            if lamp == 5 and fan_auto:
                print("❌ Manual kipas diabaikan (AUTO aktif)")
            else:
                relay.value(0 if lampStatus[idx] else 1)
                publish_status(lamp, lampStatus[idx])

    except Exception as e:
        print("❌ Error MQTT:", e)

# --- Publish Status ---
def publish_status(lamp, state):
    if client:
        data = {"lamp": lamp, "status": "ON" if state else "OFF"}
        client.publish(b"iot/lamp/status", json.dumps(data))

def publish_all_status():
    if client:
        data = {
            "lamp1": "ON" if LAMP1.value() == 0 else "OFF",
            "lamp2": "ON" if LAMP2.value() == 0 else "OFF",
            "lamp3": "ON" if LAMP3.value() == 0 else "OFF",
            "lamp4": "ON" if LAMP4.value() == 0 else "OFF",
            "fan": "ON" if FAN.value() == 0 else "OFF"
        }
        client.publish(b"iot/lamp/status", json.dumps(data))

# --- MQTT Setup ---
def connect_mqtt():
    global client
    while True:
        try:
            client = MQTTClient(CLIENT_ID, MQTT_SERVER)
            client.set_callback(sub_cb)
            client.connect()
            client.subscribe(b"iot/lamp/cmd/#")
            print("✅ MQTT Terhubung ke", MQTT_SERVER)
            break
        except Exception as e:
            print("❌ MQTT gagal:", e)
            time.sleep(5)

# --- Setup Awal ---
connect_wifi()
connect_mqtt()

# Semua relay OFF (HIGH = off)
for r in [LAMP1, LAMP2, LAMP3, LAMP4, FAN]:
    r.value(1)
BUZZER.value(0)

last_sensor = time.ticks_ms()
interval_sensor = 5000  # 5 detik

# --- Loop utama ---
while True:
    try:
        client.check_msg()
        now = time.ticks_ms()

        if time.ticks_diff(now, last_sensor) > interval_sensor:
            last_sensor = now

            # --- DHT11 ---
            try:
                dht11.measure()
                suhu = dht11.temperature()
                kelembaban = dht11.humidity()
                print("💡 LDR Value:", suhu)
            except:
                suhu, kelembaban = None, None

            # --- MQ135 ---
            gas_raw = MQ135_PIN.read()
            gas_ppm = {
                "CO": round((gas_raw / 4095) * 1000, 2),
                "CO2": round((gas_raw / 4095) * 800, 2),
                "NH4": round((gas_raw / 4095) * 500, 2)
            }

            # --- Buzzer peringatan gas ---
            if gas_ppm["CO"] > 600:
                BUZZER.value(1)
                print("🚨 Gas tinggi! CO =", gas_ppm["CO"])
            else:
                BUZZER.value(0)

            # --- LDR ---
            ldr_value = LDR_PIN.read()
            print("💡 LDR Value:", ldr_value)

            if ldr_value < 100:
                print("🌙 Gelap → Semua lampu ON")
                for i, r in enumerate([LAMP1, LAMP2, LAMP3, LAMP4]):
                    r.value(0)
                    lampStatus[i] = 1
                publish_all_status()

            # --- Kipas AUTO ---
            if fan_auto and suhu is not None:
                if suhu > 35:
                    FAN.value(0)
                    lampStatus[4] = 1
                else:
                    FAN.value(1)
                    lampStatus[4] = 0

            # --- Kirim data MQTT + Flask ---
            if suhu is not None:
                data = {
                    "temperature": suhu,
                    "humidity": kelembaban,
                    "gas": gas_ppm,
                    "ldr": ldr_value,
                    "fan_mode": "AUTO" if fan_auto else "MANUAL",
                    "lampu": {
                        "lamp1": LAMP1.value() == 0,
                        "lamp2": LAMP2.value() == 0,
                        "lamp3": LAMP3.value() == 0,
                        "lamp4": LAMP4.value() == 0,
                        "fan": FAN.value() == 0
                    }
                }

                client.publish(b"iot/monitoring", json.dumps(data))
                print("📤 MQTT Data:", data)

                try:
                    res = urequests.post(url, json=data)
                    print("📡 Flask API:", res.status_code)
                    res.close()
                except Exception as e:
                    print("❌ Gagal kirim API:", e)

            time.sleep_ms(100)

    except Exception as e:
        print("⚠ Loop error:", e)
        connect_wifi()
        connect_mqtt()
