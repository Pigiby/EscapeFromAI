import os
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from prompt_injection.defense import analyze_input, analyze_output
from prompt_injection.guardian import Guardian
from voice_negotiation.routes import register_routes as register_voice_routes
from undercover_game.routes import undercover_game_bp
import comfyui_api  # Importa il tuo script per ComfyUI

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_SECURITY_KEY"

# supports_credentials permette ai cookie di sessione di passare tra front-end e back-end
CORS(app, supports_credentials=True)

guardian = Guardian()
register_voice_routes(app)
app.register_blueprint(undercover_game_bp)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_DIR = os.path.normpath(os.path.join(BASE_DIR, "gesture_recognition", "static", "assets", "image_sequence"))
EXPECTED_FILES = 3

# Variabile globale per monitorare lo stato del thread di generazione immagini
is_running = False

def run_generation_task():
    global is_running
    is_running = True
    try:
        comfyui_api.main()
    finally:
        is_running = False

# --- GESTIONE ACCESSO ---

@app.route("/")
def index():
    # Se l'utente entra nell'indirizzo base, lo mandiamo al livello 1
    return redirect(url_for('level_1'))

# --- LIVELLO 1: PROMPT INJECTION ---
@app.route("/prompt_injection")
def level_1():
    return send_from_directory(os.path.join(BASE_DIR, "prompt_injection", "static"), "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message", "")
    threat_level = data.get("threat_level", 0)

    input_result = analyze_input(message)
    if input_result["blocked"]:
        return jsonify({
            "role": "system",
            "content": input_result['reason'],
            "threat_delta": input_result["threat_delta"]
        })

    response = guardian.respond(message, threat_level=threat_level)
    output_result = analyze_output(response, guardian.secret_code)

    # SBLOCCO LIVELLO 2: salviamo in sessione
    if output_result["leaked"]:
        session['level_1_complete'] = True
    
    return jsonify({
        "response": response,
        "leaked": output_result["leaked"],
        "suspicious": output_result["suspicious"],
        "threat_delta": input_result["threat_delta"]
    })

# --- LIVELLO 2: GESTURE RECOGNITION ---
@app.route("/gesture")
def level_2():
    # Se il livello 1 non è fatto, torna indietro
    if not session.get('level_1_complete'):
        return redirect(url_for('level_1'))
    return send_from_directory(os.path.join(BASE_DIR, "gesture_recognition", "static"), "index.html")

@app.route("/complete_level_2", methods=["POST"])
def complete_level_2():
    # Da chiamare via JS quando il puzzle è risolto
    session['level_2_complete'] = True
    return jsonify({"unlocked": True, "next": "/voice"})

@app.route('/static/assets/<path:filename>')
def serve_cipher_images(filename):
    return send_from_directory(IMAGE_DIR, filename)

# --- COMFYUI GENERATION ENDPOINTS ---

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

@app.route("/status", methods=['GET'])
def get_cipher_status():
    global is_running
    try:
        if not os.path.exists(IMAGE_DIR):
            return jsonify({"complete": False, "error": "Folder not found", "is_running": is_running}), 404
        
        # Scansiona i file nella directory
        files = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        count = len(files)
        is_complete = count >= EXPECTED_FILES
        
        return jsonify({
            "status": "completed" if is_complete else ("processing" if is_running else "idle"),
            "images_found": count,
            "complete": is_complete,
            "is_running": is_running,
            "filenames": sorted(files)
        }), 200
    except Exception as e:
        return jsonify({"complete": False, "error": str(e), "is_running": is_running}), 500

# --- UTILITY ---
@app.route("/reset")
def reset_progress():
    session.clear()
    return "Progress reset. All levels locked except Level 1."

if __name__ == "__main__":
    # Nota: mantiene la porta 8080 del server principale. 
    # Assicurati di aggiornare il frontend se prima puntava alla porta 5001!
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=True)