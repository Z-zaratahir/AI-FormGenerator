from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import preprocessing
from preprocess import clean_text, tokenize_text
import spacy

app = Flask(__name__)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

# Rate limiter
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])

# Load spaCy model once
nlp = spacy.load("en_core_web_sm")

@app.route("/process", methods=["POST"])
@limiter.limit("20 per minute")
def process_prompt():
    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt or len(prompt) < 5:
        return jsonify({"error": "Invalid prompt"}), 400

    # Preprocessing
    cleaned = clean_text(prompt)
    tokens = tokenize_text(cleaned)
    tokens_lower = [t.lower() for t in tokens]

    fields = []

    # --- NER-based field extraction ---
    doc = nlp(cleaned)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            fields.append({"label": "Name", "type": "text"})
        elif ent.label_ == "DATE":
            fields.append({"label": "Date", "type": "date"})
        elif ent.label_ == "GPE":
            fields.append({"label": "Location", "type": "text"})

    # --- Token-based field detection ---
    keyword_map = {
        "name": {"label": "Name", "type": "text"},
        "email": {"label": "Email", "type": "email"},
        "age": {"label": "Age", "type": "number"},
        "dob": {"label": "Date of Birth", "type": "date"},
        "city": {"label": "City", "type": "text"},
        "address": {"label": "Address", "type": "text"},
        "file": {"label": "Upload Document", "type": "file"},
        "upload": {"label": "Upload Document", "type": "file"},
        "fileupload": {"label": "Upload Document", "type": "file"},
        "mcq": {"label": "Multiple Choice Questions", "type": "text"},
        "mcqs": {"label": "Multiple Choice Questions", "type": "text"},
        "short": {"label": "Short Answer", "type": "text"},
        "answers": {"label": "Short Answer", "type": "text"},
        "subject": {"label": "Subject", "type": "text"},
        "marks": {"label": "Marks", "type": "number"},
        "roll": {"label": "Roll Number", "type": "text"},
    }

    existing_labels = {field["label"].lower() for field in fields}

    for token in tokens_lower:
        if token in keyword_map:
            label = keyword_map[token]["label"].lower()
            if label not in existing_labels:
                fields.append(keyword_map[token])
                existing_labels.add(label)

    return jsonify({
        "title": "Generated Form",
        "cleaned": cleaned,
        "tokens": tokens,
        "fields": fields
    })

if __name__ == "__main__":
    app.run(debug=True)
