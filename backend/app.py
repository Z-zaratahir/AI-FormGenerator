from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import spacy

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])
nlp = spacy.load("en_core_web_sm")

@app.route("/generate-form", methods=["POST"])
@limiter.limit("10 per minute")
def generate_form():
    data = request.get_json()
    prompt = data.get("prompt", "")
    if not prompt or len(prompt) < 5:
        return jsonify({"error": "Invalid prompt"}), 400

    doc = nlp(prompt)
    fields = []

    for ent in doc.ents:
        if ent.label_ == "PERSON":
            fields.append({"label": "Name", "type": "text"})
        elif ent.label_ == "DATE":
            fields.append({"label": "Date", "type": "date"})
        elif ent.label_ == "GPE":
            fields.append({"label": "Location", "type": "text"})

    return jsonify({"title": "Generated Form", "fields": fields})

if __name__ == "__main__":
    app.run(debug=True)
