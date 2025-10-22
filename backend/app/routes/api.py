from flask import Blueprint, jsonify, request, current_app
from bson import ObjectId
import time

api_bp = Blueprint("api", __name__)

# Fungsi bantu: ubah ObjectId ke string
def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    return doc

# ✅ [GET] Ambil semua data sensor
@api_bp.route("/sensor", methods=["GET"])
def get_all_sensor_data():
    try:
        collection = current_app.db["sensor_data"]
        data = list(collection.find().sort("_id", -1).limit(50))
        return jsonify([serialize_doc(d) for d in data]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ [GET] Ambil data terbaru
@api_bp.route("/sensor/latest", methods=["GET"])
def get_latest_sensor_data():
    try:
        collection = current_app.db["sensor_data"]
        data = collection.find_one(sort=[("_id", -1)])
        if data:
            return jsonify(serialize_doc(data)), 200
        else:
            return jsonify({"message": "Belum ada data"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Util: normalisasi payload agar sesuai skema Nutricomm
def _normalize_sensor_payload(raw: dict) -> dict:
    if not raw:
        return {}

    id_kebun = raw.get("id_kebun")
    if id_kebun is None:
        id_kebun = "KBG001"
    else:
        id_kebun = str(id_kebun)

    suhu = raw.get("suhu", raw.get("temperature"))
    kelembapan_udara = raw.get("kelembapan_udara", raw.get("humidity"))
    kelembapan_tanah = raw.get("kelembapan_tanah")
    cahaya = raw.get("cahaya", raw.get("ldr"))

    co2 = raw.get("co2")
    if co2 is None:
        gas = raw.get("gas") or {}
        if isinstance(gas, dict):
            co2 = gas.get("CO2") or gas.get("co2")

    timestamp = raw.get("timestamp")
    if not timestamp:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    doc = {
        "id_kebun": id_kebun,
        "suhu": suhu,
        "kelembapan_udara": kelembapan_udara,
        "kelembapan_tanah": kelembapan_tanah,
        "cahaya": cahaya,
        "co2": co2,
        "timestamp": timestamp,
    }
    return {k: v for k, v in doc.items() if v is not None}

# ✅ [POST] Tambah data sensor
@api_bp.route("/sensor", methods=["POST"])
def add_sensor_data():
    try:
        raw = request.get_json()
        if not raw:
            return jsonify({"error": "Payload kosong"}), 400
        payload = _normalize_sensor_payload(raw)
        # Validasi minimal untuk skema baru
        required_keys = ["suhu", "kelembapan_udara", "kelembapan_tanah", "cahaya", "co2"]
        for key in required_keys:
            if key not in payload:
                return jsonify({"error": f"Key '{key}' tidak ditemukan"}), 400

        collection = current_app.db["sensor_data"]
        result = collection.insert_one(payload)

        # Kirimkan update ke semua client WebSocket
        from app import socketio
        socketio.emit("sensor_update", payload, namespace="/ws")

        return jsonify({
            "message": "Data berhasil disimpan",
            "id": str(result.inserted_id)
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ [DELETE] Hapus semua data
@api_bp.route("/sensor", methods=["DELETE"])
def delete_all_sensor_data():
    try:
        collection = current_app.db["sensor_data"]
        result = collection.delete_many({})
        return jsonify({"message": f"{result.deleted_count} data dihapus"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
