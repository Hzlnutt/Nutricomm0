from flask import Blueprint, jsonify, request, current_app
from bson import ObjectId
import datetime

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

# ✅ [POST] Tambah data sensor
@api_bp.route("/sensor", methods=["POST"])
def add_sensor_data():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Payload kosong"}), 400

        # Validasi minimal agar tidak menyimpan data kosong
        required_keys = ["suhu", "kelembaban", "gas", "ldr"]
        for key in required_keys:
            if key not in payload:
                return jsonify({"error": f"Key '{key}' tidak ditemukan"}), 400

        collection = current_app.db["sensor_data"]
        payload["timestamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result = collection.insert_one(payload)

        # Kirimkan update ke semua client WebSocket
        from app import socketio
        socketio.emit("sensor_update", payload)

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
