import os
from flask import Flask
from flask_socketio import SocketIO
from pymongo import MongoClient
from .config import Config
from app.routes.api import api_bp  # pastikan folder structure: app/routes/api.py

socketio = SocketIO(async_mode='threading')

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Inisialisasi MongoDB
    mongo = MongoClient(app.config['MONGO_URI'])
    db_name = app.config['MONGO_URI'].split('/')[-1] or "iot_db"
    app.db = mongo[db_name]

    # Register blueprint API
    app.register_blueprint(api_bp, url_prefix="/api")

    # Inisialisasi SocketIO
    socketio.init_app(app)

    # Jalankan MQTT client di background
    try:
        from .mqtt_client import start_mqtt
        start_mqtt(app, socketio)
    except Exception as e:
        print(f"[WARNING] MQTT client tidak bisa dijalankan: {e}")

    return app
