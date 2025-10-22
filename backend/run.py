from app import create_app, socketio

app = create_app()

@app.route('/')
def index():
    return "<h1>🚀 Flask Backend Aktif!</h1><p>MQTT sudah terkoneksi dengan baik.</p>"

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
