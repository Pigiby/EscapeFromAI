from flask import Flask, jsonify, request
from flask_cors import CORS  # <--- IMPORTANTE
from pathlib import Path
import threading
import comfyui_api  # Importiamo il tuo script main.py
import os

app = Flask(__name__)
CORS(app)

OUTPUT_DIR = Path("static/assets/image_sequence")
EXPECTED_FILES = 3

# Variabile globale per monitorare lo stato del thread
is_running = False

def run_generation_task():
    global is_running
    is_running = True
    try:
        comfyui_api.main()
    finally:
        is_running = False

@app.route('/generate', methods=['POST'])
def generate():
    global is_running
    if is_running:
        return jsonify({"message": "Generazione già in corso...", "status": "busy"}), 400
    
    # Avvia il thread in background
    thread = threading.Thread(target=run_generation_task)
    thread.start()
    
    return jsonify({
        "message": "Generazione avviata con successo",
        "status": "started"
    }), 202

@app.route('/status', methods=['GET'])
def check_status():
    images = list(OUTPUT_DIR.glob("*.png")) if OUTPUT_DIR.exists() else []
    count = len(images)
    is_complete = count >= EXPECTED_FILES
    print(count)
    return jsonify({
        "status": "completed" if is_complete else ("processing" if is_running else "idle"),
        "images_found": count,
        "complete": is_complete,
        "is_running": is_running,
        "filenames": [f.name for f in images]
    }), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)