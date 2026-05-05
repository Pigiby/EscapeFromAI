import os
from flask import Flask, request, jsonify, send_from_directory, session, redirect
from flask_cors import CORS
from prompt_injection.defense import analyze_input, analyze_output
from prompt_injection.guardian import Guardian

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_SECURITY_KEY"
CORS(app)
guardian = Guardian()

# --- THE PATH FIX ---
# This finds the directory where server.py lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# This creates an absolute path to the images regardless of where you launch the script
IMAGE_DIR = os.path.normpath(os.path.join(BASE_DIR, "gesture_recognition","static","assets", "image_sequence"))

print(f"--- SERVER STARTING ---")
print(f"Targeting Image Directory: {IMAGE_DIR}")

# Check if the folder actually exists on startup to warn you immediately
if not os.path.exists(IMAGE_DIR):
    print(f"CRITICAL ERROR: The folder {IMAGE_DIR} does not exist!")
    print(f"Please ensure your folder structure matches this path.")
# ---------------------

@app.route("/")
def home():
    return send_from_directory(os.path.join(BASE_DIR, "prompt_injection", "static"), "index.html")

@app.route("/gesture")
def gesture_level():
    return send_from_directory(os.path.join(BASE_DIR, "gesture_recognition", "static"), "index.html")

# Serves the AI-generated images
@app.route('/static/assets/<path:filename>')
def serve_cipher_images(filename):
    # This will now correctly map the URL to the physical folder
    print(IMAGE_DIR)  # Debugging line to confirm paths
    return send_from_directory(IMAGE_DIR, filename)

@app.route("/status")
def get_cipher_status():
    try:
        if not os.path.exists(IMAGE_DIR):
            return jsonify({"complete": False, "error": "Folder not found"}), 404
            
        files = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        return jsonify({
            "complete": len(files) > 0,
            "filenames": sorted(files)
        })
    except Exception as e:
        return jsonify({"complete": False, "error": str(e)}), 500

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

    if output_result["leaked"]:
        session['level_1_complete'] = True
    
    return jsonify({
        "response": response,
        "leaked": output_result["leaked"],
        "suspicious": output_result["suspicious"],
        "threat_delta": input_result["threat_delta"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)