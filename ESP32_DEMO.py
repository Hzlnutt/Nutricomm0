from machine import Pin, ADC, I2C
import network, time, json, dht, urequests
from umqtt.simple import MQTTClient

# === Konfigurasi sensor Nutricomm ===
# DHT22 (gunakan DHT22 class tapi masih kompatibel di import 'dht')
DHT_PIN = Pin(15, Pin.IN)
dht_sensor = dht.DHT22(DHT_PIN)

# Soil moisture analog (ubah pin sesuai rangkaian)
SOIL_PIN = ADC(Pin(33))
SOIL_PIN.atten(ADC.ATTN_11DB)
SOIL_PIN.width(ADC.WIDTH_12BIT)

# BH1750 (I2C light sensor) — jika tidak ada, fallback ke LDR
I2C_SCL = Pin(22)
I2C_SDA = Pin(21)
i2c = I2C(0, scl=I2C_SCL, sda=I2C_SDA, freq=100000)

def bh1750_read_lux():
    try:
        addr = 0x23
        # Start measurement in one-time H-Resolution mode
        i2c.writeto(addr, b"\x20")
        time.sleep_ms(180)
        data = i2c.readfrom(addr, 2)
        raw = (data[0] << 8) | data[1]
        return int(raw / 1.2)
    except Exception:
        return None

# MQ135 (analog)
MQ135_PIN = ADC(Pin(34))
MQ135_PIN.atten(ADC.ATTN_11DB)
MQ135_PIN.width(ADC.WIDTH_12BIT)

# Fallback LDR (opsional) jika BH1750 tidak ada
LDR_PIN = ADC(Pin(32))
LDR_PIN.atten(ADC.ATTN_11DB)
LDR_PIN.width(ADC.WIDTH_12BIT)

# --- WiFi & MQTT ---
# Ubah sesuai lingkungan Anda
SSID = "hotspotkeren"
PASSWORD = "87654321"

# MQTT broker dan backend host diselaraskan dengan backend baru
MQTT_SERVER = "192.168.0.182"   # Broker MQTT
CLIENT_ID = "ESP32Client"
BACKEND_HOST = "192.168.0.182"  # Host Flask backend
HTTP_URL = "http://%s:5000/api/sensor" % BACKEND_HOST

# Identitas kebun untuk Nutricomm
ID_KEBUN = "KBG001"

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

def sub_cb(topic, msg):
    # Tidak ada kontrol; hanya placeholder jika nanti diperlukan
    pass

# --- MQTT Setup ---
def connect_mqtt():
    global client
    while True:
        try:
            client = MQTTClient(CLIENT_ID, MQTT_SERVER)
            client.set_callback(sub_cb)
            client.connect()
            print("✅ MQTT Terhubung ke", MQTT_SERVER)
            break
        except Exception as e:
            print("❌ MQTT gagal:", e)
            time.sleep(5)

# --- Setup Awal ---
connect_wifi()
connect_mqtt()

client = None

last_sensor = time.ticks_ms()
interval_sensor = 5000  # 5 detik

# --- Loop utama ---
while True:
    try:
        client.check_msg()
        now = time.ticks_ms()

        if time.ticks_diff(now, last_sensor) > interval_sensor:
            last_sensor = now

            # --- DHT22 ---
            try:
                dht_sensor.measure()
                suhu = dht_sensor.temperature()
                kelembaban_udara = dht_sensor.humidity()
                print("🌡️ Suhu:", suhu, " Kelembapan Udara:", kelembaban_udara)
            except:
                suhu, kelembaban_udara = None, None

            # --- MQ135 ---
            gas_raw = MQ135_PIN.read()
            gas_ppm = {
                "CO": round((gas_raw / 4095) * 1000, 2),
                "CO2": round((gas_raw / 4095) * 800, 2),
                "NH4": round((gas_raw / 4095) * 500, 2)
            }

            # --- Cahaya --- prefer BH1750; fallback LDR
            lux = bh1750_read_lux()
            if lux is None:
                lux = LDR_PIN.read()
            print("💡 Cahaya:", lux)

            if ldr_value < 100:
                print("🌙 Gelap → Semua lampu ON")
                for i, r in enumerate([LAMP1, LAMP2, LAMP3, LAMP4]):
                    r.value(0)
                    lampStatus[i] = 1
                publish_all_status()

            # --- Kirim data MQTT + HTTP ke backend Nutricomm ---
            if suhu is not None:
                # Skema Nutricomm
                payload = {
                    "id_kebun": ID_KEBUN,
                    "suhu": suhu,
                    "kelembapan_udara": kelembaban_udara,
                    # Soil moisture: ubah mapping sesuai kalibrasi sensor Anda
                    "kelembapan_tanah": max(0, min(100, int((4095 - SOIL_PIN.read()) * 100 / 4095))),
                    "cahaya": lux,
                    "co2": gas_ppm.get("CO2"),
                    "timestamp": None  # biarkan backend mengisi jika None
                }

                # Publish ke MQTT
                try:
                    client.publish(b"iot/monitoring", json.dumps(payload))
                    print("📤 MQTT Nutricomm:", payload)
                except Exception as e:
                    print("❌ Gagal publish MQTT:", e)

                # Kirim HTTP ke backend (opsional, sebagai fallback)
                try:
                    headers = {"Content-Type": "application/json"}
                    res = urequests.post(HTTP_URL, data=json.dumps(payload), headers=headers)
                    print("📡 HTTP API:", res.status_code)
                    res.close()
                except Exception as e:
                    print("❌ Gagal kirim HTTP:", e)

            time.sleep_ms(100)

    except Exception as e:
        print("⚠ Loop error:", e)
        connect_wifi()
        connect_mqtt()
