#app2.py:
from html import entities
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import spacy
from spacy.matcher import Matcher
import copy
#from spacy.tokens import Span
#from spacy.util import filter_spans
from rapidfuzz import process
import re
import json
import pytz
from transformers import pipeline
from textblob import TextBlob

app = Flask(__name__)
CORS(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])

print("Loading spaCy model...")
nlp = spacy.load("en_core_web_sm")
print("Model loaded.")

# --- Data Loading Function ---
def load_knowledge_base(fields_path, templates_path):
    try:
        with open(fields_path, 'r', encoding='utf-8') as f:
            fields_data = json.load(f)
        with open(templates_path, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)
        print("Knowledge base loaded successfully from JSON files.")
        return fields_data, templates_data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"FATAL: Could not load or parse knowledge base file. Error: {e}")
        exit(1)



class FieldDefinition:
    def __init__(self, id, label, type, patterns=None, fuzzy_keywords=None, validation=None, options=None, **kwargs):
        self.id = id
        self.label = label
        self.type = type
        # default to empty list if no patterns provided
        self.patterns = patterns or []
        self.fuzzy_keywords = fuzzy_keywords or []
        self.validation = validation or {}
        self.options = options or []

def make_dynamic_def(id_str):
        return FieldDefinition(
            id=id_str,
            label=id_str.replace("_", " ").title(),
            type="text",
            validation={},
            options=[]
        )


# --- The Form Generator Engine ---
# In app4.py, replace the entire FormGenerator class with this:

class FormGenerator:
    def __init__(self, fields_data, templates_data):
        field_definitions = [FieldDefinition(**data) for data in fields_data]
        self.field_map = {f.id: f for f in field_definitions}
        self.fuzzy_map = {kw.lower(): f.id for f in field_definitions for kw in f.fuzzy_keywords}
        for field in field_definitions:
            self.fuzzy_map[field.label.lower()] = field.id
            
        self.form_templates = self._resolve_template_aliases(templates_data)

        model_path = "./FormGeneratorModel"
        print(f"Loading fine-tuned model from: {model_path}")
        try:
            self.classifier = pipeline("token-classification", model=model_path, aggregation_strategy="simple")
            print("Hugging Face model loaded successfully.")
        except Exception as e:
            print(f"FATAL: Could not load Hugging Face model. Error: {e}")
            exit(1)

        # ─── TIER 2: off‑the‑shelf FLAN‑T5‑Large few‑shot fallback ────────────
        print("Loading base FLAN‑T5‑Large for Tier 2 fallback…")
        try:
            self.seq2seq = pipeline(
            "text2text-generation",
            model="google/flan-t5-large",
            tokenizer="google/flan-t5-large",
            device=-1,              # forces CPU
            max_new_tokens=64,      # use the newer argument name
            do_sample=False
            )

            print("✅ Loaded google/flan-t5-large")
        except Exception as e:
            print(f"FATAL: could not load FLAN‑T5‑Large. Error: {e}")
            exit(1)
        # ────────────────────────────────────────────────────────────────────


    def _resolve_template_aliases(self, templates):
        resolved = {}
        for key, value in templates.items():
            while isinstance(value, str):
                value = templates.get(value, {})
            resolved[key] = value
        for key, value in resolved.items():
            if isinstance(value, dict):
                if "fields" not in value: value["fields"] = []
                if "seeds" not in value: value["seeds"] = []
        return resolved
    
    def tier1(self, prompt: str):
        corrected_prompt = str(TextBlob(prompt).correct())
        if corrected_prompt != prompt:
            print(f"Spell-corrected prompt: '{prompt}' -> '{corrected_prompt}'")
        entities = self.classifier(corrected_prompt)
        print(f"Model Entities Found: {entities}")

        def get_field_id_from_word(word):
            candidates = list(self.fuzzy_map.keys()) + list(self.field_map.keys())
            match_tuple = process.extractOne(word, candidates, score_cutoff=80)
            if match_tuple:
                return self.fuzzy_map.get(match_tuple[0]) or (match_tuple[0] if match_tuple[0] in self.field_map else None)
            return None

        final_fields_map = {}
        detected_template_names = []
        
        rating_min, rating_max = 1, 5
        rating_range_found = False
        rating_match = re.search(r"(?:rating|rate|score)\s*(?:\(|from|\:)?\s*(\d+)\s*(?:to|-)\s*(\d+)", corrected_prompt, re.IGNORECASE)
        if not rating_match and len(corrected_prompt.split()) < 10:
            rating_match = re.search(r"(\d+)\s*(?:to|-)\s*(\d+)", corrected_prompt, re.IGNORECASE)

        if rating_match:
            try:
                num1, num2 = int(rating_match.group(1)), int(rating_match.group(2))
                rating_min, rating_max = min(num1, num2), max(num1, num2)
                rating_range_found = True
                print(f"DEBUG: Rating range found in prompt: {rating_min} to {rating_max}")
            except (ValueError, IndexError): pass
        else:
            print(f"DEBUG: No rating range found in prompt. Using defaults: {rating_min} to {rating_max}")

        is_explicit_rating_command = bool(re.search(r"\b(with|add|include|create|make)\b.*?\b(rating|rate|score)\b", corrected_prompt, re.IGNORECASE))

        # Step 2: If not an explicit command, check the heuristic for a single rating field.
        is_heuristic_rating_match = False
        if not is_explicit_rating_command:
            is_short = len(corrected_prompt.split()) < 8
            mentions_rating_keyword = bool(re.search(r"\b(rating|rate|score|field)\b", corrected_prompt, re.IGNORECASE))
            has_form_type_entity = any(e.get('entity_group') == 'FORM_TYPE' for e in entities)
            if is_short and mentions_rating_keyword and not has_form_type_entity:
                is_heuristic_rating_match = True

        # Combine the checks. If either is true, it's a single-field prompt.
        is_field_specific_prompt = is_explicit_rating_command or is_heuristic_rating_match

        # --- Decision Branching ---
        # This structure ensures ONLY ONE of these blocks can run.

        if is_field_specific_prompt:
            # BRANCH 1: Create a single rating field.
            print("DEBUG: Detected field-specific prompt for RATING.")
            rating_field = FieldDefinition(
                id="RATING", label="Rating", type="rating",
                validation={'min': rating_min, 'max': rating_max}, options=[]
            )
            final_fields_map["RATING"] = rating_field

        else:
            # BRANCH 2: This is a full form, so search for a template.
            # First, try to match based on a FORM_TYPE entity.
            form_type_entities = [e['word'] for e in entities if e.get('entity_group') == 'FORM_TYPE']
            if form_type_entities:
                entity_word = form_type_entities[0]
                match = process.extractOne(entity_word, self.form_templates.keys(), score_cutoff=85)
                if match:
                    tid = match[0]
                    detected_template_names.append(tid)
                    print(f"DEBUG: Matched template '{tid}' via FORM_TYPE entity '{entity_word}'.")

            # If no entity match, fall back to fuzzy matching seeds.
            if not detected_template_names:
                print("DEBUG: No FORM_TYPE entity found. Falling back to fuzzy matching seeds.")
                best_score, best_key = 0, None
                for key, template in self.form_templates.items():
                    seeds = template.get("seeds", [])
                    if not seeds: continue
                    
                    match_tuple = process.extractOne(corrected_prompt, seeds, score_cutoff=90)
                    if match_tuple and match_tuple[1] > best_score:
                        best_score, best_key = match_tuple[1], key
                
                if best_key:
                    detected_template_names.append(best_key)
                    print(f"DEBUG: Matched template '{best_key}' via fuzzy seed matching.")

            # If a template was found by either method, populate its fields.
            if detected_template_names:
                tid = detected_template_names[0]
                template_fields = self.form_templates.get(tid, {}).get("fields", [])
                for item in template_fields:
                    fid = item.get('id') if isinstance(item, dict) else item
                    if fid in self.field_map and fid not in final_fields_map:
                        field_obj = copy.deepcopy(self.field_map[fid])
                        if field_obj.type == 'rating' and rating_range_found:
                            field_obj.validation['min'] = rating_min
                            field_obj.validation['max'] = rating_max
                        final_fields_map[fid] = field_obj
        
        field_entities = sorted([e for e in entities if e.get('entity_group') == 'FIELD_NAME'], key=lambda x: x['start'])
        ordered_field_ids = []
        for field_entity in field_entities:
            field_id = get_field_id_from_word(field_entity['word'])
            if field_id:
                if field_id not in final_fields_map:
                    if field_id in self.field_map:
                        final_fields_map[field_id] = copy.deepcopy(self.field_map[field_id])
                    else:
                        final_fields_map[field_id] = make_dynamic_def(field_id)
                if field_id not in ordered_field_ids:
                    ordered_field_ids.append(field_id)

        fields_to_remove = set()
        negation_entities = [e for e in entities if e.get('entity_group') == 'NEGATION']
        for neg_entity in negation_entities:
            potential_targets = [fe for fe in field_entities if fe['start'] > neg_entity['end']]
            if not potential_targets: continue
            closest_field_entity = min(potential_targets, key=lambda fe: fe['start'] - neg_entity['end'])
            field_id_to_remove = get_field_id_from_word(closest_field_entity['word'])
            if field_id_to_remove: fields_to_remove.add(field_id_to_remove)
        for field_id in fields_to_remove:
            final_fields_map.pop(field_id, None)
            if field_id in ordered_field_ids: ordered_field_ids.remove(field_id)
        
        # --- FINAL ASSEMBLY ---
        # `final_fields_map` now contains the correct FieldDefinition objects with correct validation.
        # We now create a sorted list of these objects.
        final_ordered_objects = []
        processed_ids = set()
        
        # Use a consistent order: first, manually ordered fields, then any others.
        id_order_list = ordered_field_ids + [fid for fid in final_fields_map if fid not in ordered_field_ids]
        if is_field_specific_prompt and "RATING" not in id_order_list:
            id_order_list.insert(0, "RATING")

        for fid in id_order_list:
            if fid in final_fields_map and fid not in processed_ids:
                final_ordered_objects.append(final_fields_map[fid])
                processed_ids.add(fid)

        final_template = detected_template_names[0] if detected_template_names else "custom"
        return final_ordered_objects, final_template


    def tier2(self, prompt: str):
        instruction = (
            "### FORM GENERATOR INSTRUCTIONS:\n"
            "- You will be given a REQUEST describing the form the user wants.\n"
            "- OUTPUT: A JSON array of exactly 2–4 field IDs (ALL CAPS, underscore-separated), with no extra text or punctuation.\n"
            "- IMPORTANT: You must NEVER repeat the same field ID (NEVER). If unsure, leave the list shorter.\n\n"
            "### EXAMPLES:\n"
        )
        examples = [
            ("Need a form to book a hotel stay", ["CHECKIN_DATE", "CHECKOUT_DATE", "ROOM_TYPE", "GUEST_COUNT"]),
            ("Let users reach out with their queries", ["FULL_NAME", "EMAIL", "PHONE_NUMBER", "MESSAGE"]),
            ("Help me collect donations online", ["FULL_NAME", "EMAIL", "AMOUNT", "PAYMENT_METHOD"]),
            ("I need a form for booking consultations", ["FULL_NAME", "EMAIL", "PREFERRED_DATE", "TOPIC"]),
            ("People should be able to plan their travel", ["DESTINATION", "DEPARTURE_DATE", "RETURN_DATE", "TRAVELERS"])
        ]
        for req, fld in examples: instruction += f"REQUEST: {req}\nFIELDS: {json.dumps(fld)}\n\n"
        instruction += (
            "### BAD EXAMPLE:\n"
            "REQUEST: Write a form so we can know about our community\n"
            "FIELDS: [\"COMMUNITIES\",\"COMMUNITIES\",\"COMMUNITIES\"]\n\n"
            "### YOUR TURN:\n"
            f"REQUEST: {prompt}\n"
            "FIELDS:"
        )
        try:
            out = self.seq2seq(instruction)[0]["generated_text"]
        except Exception as e:
            print(f"Tier 2 model failed: {e}"); return [], "custom"
        
        raw_ids = []
        match = re.search(r"\[.*?\]", out, re.DOTALL)
        if match:
            try:
                raw_fields = json.loads(match.group(0))
                if isinstance(raw_fields, list):
                    def normalize(fid):
                        s = str(fid).strip().upper(); s = re.sub(r"_\d+$", "", s)
                        if s.endswith("IES"): s = s[:-3] + "Y"
                        elif s.endswith("S") and not s.endswith("SS"): s = s[:-1]
                        return s
                    seen, unique = set(), []
                    for f in raw_fields:
                        norm = normalize(f)
                        if norm not in seen: seen.add(norm); unique.append(norm)
                    raw_ids = unique
            except json.JSONDecodeError: pass
        if not raw_ids:
            caps = re.findall(r"\b([A-Z_]{2,})\b", out)
            seen, unique = set(), []
            for f in caps:
                norm = re.sub(r"_\d+$", "", f)
                if norm not in seen: seen.add(norm); unique.append(norm)
            raw_ids = unique

        final_defs = [self.field_map.get(fid) or make_dynamic_def(fid) for fid in raw_ids[:4]]
        return final_defs, "custom"


    def process_prompt(self, prompt: str):
        # `tier1` and `tier2` now both return a list of FieldDefinition objects
        fields, template = self.tier1(prompt)
        if not fields:
            return self.tier2(prompt)
        return fields, template

# --- Main Application Setup ---
fields_data, templates_data = load_knowledge_base('fields.json', 'templates.json')
form_gen = FormGenerator(fields_data, templates_data)

@app.route("/process", methods=["POST"])
@limiter.limit("2 per second")
def process_prompt_route():
    data = request.get_json()
    if not data or not (prompt := data.get("prompt")):
        return jsonify({"error": "Prompt is empty or invalid request"}), 400
    
    cleaned = prompt.strip()
    if not cleaned or cleaned.isdigit():
        return jsonify({"error": "Prompt is empty or invalid. Please provide some text."}), 400

    # `process_prompt` now returns the final, configured list of FieldDefinition objects.
    generated_defs, template_name = form_gen.process_prompt(prompt)
    
    if not generated_defs:
        return jsonify({"title": "Could not generate form", "prompt": prompt, "fields": [], "template": "none", "message": "I couldn't understand the type of form you want. Try being more specific, like 'a contact form' or 'an internship application form'."})
        
    # All redundant logic is removed. We now simply convert the final objects to dictionaries for the JSON response.
    schema = [
        {
            "id": f.id, "label": f.label, "type": f.type,
            "validation": f.validation, "options": f.options
        }
        for f in generated_defs
    ]

    return jsonify({
        "title": "Generated Form",
        "prompt": prompt,
        "template": template_name,
        "fields": schema
    })

# --- SERVER-SIDE VALIDATION HELPER (Unchanged) ---
def validate_submission(values: dict, schema: list):
    errors = {}
    for field in schema:
        fid   = field["id"]
        rules = field.get("validation", {})
        val   = values.get(fid, "")

        if rules.get("required") and not val:
            errors[fid] = "This field is required."
            continue
        if not val: continue

        if "minLength" in rules and len(val) < rules["minLength"]: errors[fid] = f"Must be at least {rules['minLength']} characters."
        if "maxLength" in rules and len(val) > rules["maxLength"]: errors[fid] = f"Must be no more than {rules['maxLength']} characters."
        if (p := rules.get("pattern")) and not re.fullmatch(p, val): errors[fid] = "Invalid format."
        
        rule = rules.get("rule")
        if rule == "email_format" and not re.fullmatch(r"^[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}$", val): errors[fid] = "Must be a valid email address."
        elif rule == "phone_number" and not re.fullmatch(r"\d{11}", val): errors[fid] = "Must be exactly 11 digits."
        elif rule == "credit_card_format" and not re.fullmatch(r"\d{13,19}", val.replace(" ", "")): errors[fid] = "Must be 13–19 digits (spaces allowed)."
        elif rule == "expiry_format" and not re.fullmatch(r"(0[1-9]|1[0-2])\/([2-9]\d)", val): errors[fid] = "Must be in MM/YY format."
        elif rule == "national_id" and not re.fullmatch(r"\d{5}-\d{7}-\d", val): errors[fid] = "Invalid National ID format."
        elif rule == "alphanumeric" and not re.fullmatch(r"[A-Za-z0-9]+", val): errors[fid] = "Only letters and numbers allowed."
        elif rule == "available_username" and val.lower() in ("admin","test","root"): errors[fid] = "Username is already taken."
        
        if "PASSWORD" in values and "CONFIRM_PASSWORD" in values and values["PASSWORD"] != values["CONFIRM_PASSWORD"]:
            errors["CONFIRM_PASSWORD"] = "Passwords do not match."

        try:
            if field.get("type") == "number": float(val)
            elif field.get("type") == "date": from datetime import datetime; datetime.strptime(val, "%Y-%m-%d")
        except ValueError: errors[fid] = f"Must be a valid {field.get('type')}."
        
        if field.get("type") == "rating" and val:
            try:
                r, mn, mx = int(val), rules.get("min",1), rules.get("max",5)
                if r < mn or r > mx: errors[fid] = f"Rating must be between {mn} and {mx}."
            except ValueError: errors[fid] = "Rating must be a number."

        if re.search(r"<[^>]+>", val): errors[fid] = "HTML tags are not allowed."
    return errors

@app.route("/submit", methods=["POST"])
@limiter.limit("5 per minute")
def submit_route():
    payload = request.get_json(force=True)
    values, schema  = payload.get("values", {}), payload.get("schema", [])
    print(">>> /submit values:", values)
    print(">>> /submit schema:", [f['id'] + ":" + str(f.get('validation')) for f in schema])
    errs = validate_submission(values, schema)
    if errs: return jsonify({"success": False, "errors": errs}), 400
    return jsonify({"success": True, "message": "Form submitted successfully."})

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
