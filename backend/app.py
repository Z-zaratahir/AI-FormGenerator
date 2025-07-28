#app2.py:
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

# --- The Form Generator Engine ---
class FormGenerator:
    def __init__(self, fields_data, templates_data):
        field_definitions = [FieldDefinition(**data) for data in fields_data]
        self.field_map = {f.id: f for f in field_definitions}
        self.fuzzy_map = {kw: f.id for f in field_definitions for kw in f.fuzzy_keywords}
        for field in field_definitions:
            self.fuzzy_map[field.label.lower()] = field.id
            
        self.matcher = self._build_matcher()
        self.form_templates = self._resolve_template_aliases(templates_data)

        model_path = "./FormGeneratorModel"
        print(f"Loading fine-tuned model from: {model_path}")
        try:
            self.classifier = pipeline("token-classification", model=model_path, aggregation_strategy="simple")
            print("Hugging Face model loaded successfully.")
        except Exception as e:
            print(f"FATAL: Could not load Hugging Face model. Error: {e}")
            self.classifier = None
            exit(1)

    def _resolve_template_aliases(self, templates):
        # resolve all string aliases (e.g., "application": "job_application")
        resolved = {}
        for key, value in templates.items():
            while isinstance(value, str):
                value = templates.get(value, {})
            resolved[key] = value
        
        # Ensring all templates have the required keys for consistency
        for key, value in resolved.items():
            if isinstance(value, dict):
                if "fields" not in value: value["fields"] = []
                if "seeds" not in value: value["seeds"] = []
        return resolved

    def _build_matcher(self):
        matcher = Matcher(nlp.vocab)
        
        matcher.add("ATTRIBUTE", [
            [{"LOWER": {"IN": ["required", "mandatory", "compulsory", "essential"]}}],
            [{"LOWER": "not"}, {"LOWER": "optional"}]
        ])
        
        matcher.add("QUANTITY", [
            [{"like_num": True}]
        ])
        
        matcher.add("NEGATION", [
            [{"LOWER": "without"}],
            [{"LOWER": "no"}],
            [{"LOWER": "don't"}, {"LOWER": "include"}],
            [{"LOWER": "except"}, {"LOWER": "for"}]
        ])
        
        return matcher
    
    def filter_overlapping_matches(self, matches):
        """
        Filters out shorter, overlapping matches to mimic a "greedy" behavior.
        For example, if we have a match on "not required" (ATTR_OPTIONAL) and
        another on just "not" (LOGIC_NEGATION), this will discard the shorter one.
        """
        if not matches:
            return []

        # Sort matches by start position, then by length (longest first)
        sorted_matches = sorted(matches, key=lambda m: (m[1], -(m[2] - m[1])))
        
        filtered = []
        last_end = -1
        for match in sorted_matches:
            _, start, end = match
            # If the current match doesn't overlap with the last one we kept, add it.
            if start >= last_end:
                filtered.append(match)
                last_end = end
        return filtered
    
    def word_to_num(self, word):
        num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        return num_map.get(word.lower())

    def find_all_negated_nouns(self, doc, start_index):
        nouns = []
        for i in range(start_index, min(start_index + 8, len(doc))):
            token = doc[i]
            if token.pos_ == "VERB" and nouns: break
            if token.pos_ == "NOUN":
                compound_noun_span = doc[i:i+2] if i + 1 < len(doc) and doc[i+1].pos_ in ['NOUN', 'PROPN'] else doc[i:i+1]
                if not any(compound_noun_span.text in n for n in nouns):
                     nouns.append(compound_noun_span.text)
        return nouns
    
    def post_process_name_fields(self, fields):
        has_first = any(f['id'] == 'FIRST_NAME' for f in fields)
        
        has_last = any(f['id'] == 'LAST_NAME' for f in fields)
        if has_first and has_last:
            return [f for f in fields if f['id'] != 'FULL_NAME']
        return fields


    def process_prompt(self, prompt):
        entities = self.classifier(prompt)
        print(f"Model Entities Found: {entities}")
        doc = nlp(prompt)
        
        final_fields_map = {}
        detected_template_names = []

        for entity in entities:
            if entity['entity_group'] == 'FORM_TYPE':
                match = process.extractOne(entity['word'], self.form_templates.keys(), score_cutoff=85)
                if match:
                    template_id = match[0]
                    if template_id not in detected_template_names:
                        detected_template_names.append(template_id)
                        template_data = self.form_templates.get(template_id, {})
                        while isinstance(template_data, str):
                            template_data = self.form_templates.get(template_data, {})
                        for item in template_data.get("fields", []):
                            field_id = item.get('id') if isinstance(item, dict) else item
                            if self.field_map.get(field_id):
                                final_fields_map[field_id] = copy.deepcopy(self.field_map[field_id])
        
        num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        
        for entity in entities:
            if entity['entity_group'] == 'FIELD_NAME':
                match = process.extractOne(entity['word'], self.fuzzy_map.keys(), score_cutoff=85)
                if match:
                    field_id_base = self.fuzzy_map[match[0]]
                    
                    num = 1
                    quantity_entity = min([e for e in entities if e['entity_group'] == 'QUANTITY' and e['start'] < entity['start']], 
                                        key=lambda x: entity['start'] - x['start'], default=None)
                    
                    if quantity_entity and (entity['start'] - quantity_entity['end'] < 15):
                        num_word = quantity_entity['word'].lower()
                        num = int(num_word) if num_word.isdigit() else num_map.get(num_word, 1)

                    if num > 1:
                        for i in range(num):
                            field_id = f"{field_id_base}_{i+1}"
                            if field_id not in final_fields_map:
                                field_def = copy.deepcopy(self.field_map[field_id_base])
                                field_def.id = field_id
                                field_def.label = f"{field_def.label} #{i+1}"
                                final_fields_map[field_id] = field_def
                    else:
                        if field_id_base not in final_fields_map:
                            final_fields_map[field_id_base] = copy.deepcopy(self.field_map[field_id_base])

        for entity in entities:
            if entity['entity_group'] == 'NEGATION':
                target_field_entity = min([e for e in entities if e['entity_group'] == 'FIELD_NAME' and e['start'] >= entity['end']], 
                                        key=lambda x: x['start'], default=None)
                if target_field_entity:
                    match = process.extractOne(target_field_entity['word'], self.fuzzy_map.keys(), score_cutoff=80)
                    if match:
                        field_id_to_remove = self.fuzzy_map[match[0]]
                        if field_id_to_remove in final_fields_map:
                            del final_fields_map[field_id_to_remove]
        
        for entity in entities:
            if entity['entity_group'] == 'ATTRIBUTE':
                target_field_entity = min([e for e in entities if e['entity_group'] == 'FIELD_NAME' and abs(e['start'] - entity['start']) < 40], 
                                        key=lambda x: abs(x['start'] - entity['start']), default=None)
                if target_field_entity:
                    match = process.extractOne(target_field_entity['word'], self.fuzzy_map.keys(), score_cutoff=80)
                    if match:
                        field_id_to_mod = self.fuzzy_map[match[0]]
                        for key in list(final_fields_map.keys()):
                            if key.startswith(field_id_to_mod):
                                final_fields_map[key].validation['required'] = True

        final_fields = []
        for field_def in final_fields_map.values():
            final_fields.append({
                "id": field_def.id, "label": field_def.label, "type": field_def.type,
                "validation": field_def.validation, "options": field_def.options
            })
            
        final_template = detected_template_names[0] if detected_template_names else "custom"
        return final_fields, final_template

    
# --- Main Application Setup ---
fields_data, templates_data = load_knowledge_base('fields.json', 'templates.json')
form_gen = FormGenerator(fields_data, templates_data)

@app.route("/process", methods=["POST"])
@limiter.limit("2 per second")
def process_prompt_route():
    data = request.get_json()
    if not data or not (prompt := data.get("prompt")):
        return jsonify({"error": "Prompt is empty or invalid request"}), 400
    
    # ─── Step 0: Basic Prompt Quality Check ────────────────────────────────
    cleaned = prompt.strip()
    word_count = len(cleaned.split())

    # Reject if too short, too few words, digits only, or trivial words
    if (
        len(cleaned) < 8 or
        word_count < 2 or
        cleaned.isdigit() or
        re.fullmatch(r"[A-Za-z]{1,4}", cleaned)  # e.g. "abc", "dfdb"
    ):
        return jsonify({
            "error": "Prompt too short or vague. Please provide at least 3 words and 10 characters."}), 400

    


    generated_fields, template_name = form_gen.process_prompt(prompt)
    if not generated_fields:
        return jsonify({"title": "Could not generate form", "prompt": prompt, "fields": [], "template": "none", "message": "I couldn't understand the type of form you want. Try being more specific, like 'a contact form' or 'an internship application form'."})
        
    return jsonify({"title": "Generated Form", "prompt": prompt, "template": template_name, "fields": generated_fields})

# ─── SERVER‑SIDE VALIDATION HELPER ─────────────────────────────────────────
def validate_submission(values: dict, schema: list):
    errors = {}
    for field in schema:
        fid   = field["id"]
        rules = field.get("validation", {})
        val   = values.get(fid, "")

        # 1) Required?
        if rules.get("required") and not val:
            errors[fid] = "This field is required."
            continue

        # 2) Skip further checks if empty
        if not val:
            continue

        # 3) Length checks
        if "minLength" in rules and len(val) < rules["minLength"]:
            errors[fid] = f"Must be at least {rules['minLength']} characters."
        if "maxLength" in rules and len(val) > rules["maxLength"]:
            errors[fid] = f"Must be no more than {rules['maxLength']} characters."

        # 4) Regex pattern
        pattern = rules.get("pattern")
        if pattern and not re.fullmatch(pattern, val):
            errors[fid] = "Invalid format."

        # 5) “rule” shortcuts
        rule = rules.get("rule")
        if rule == "email_format":
            if not re.fullmatch(r"^[\w\.-]+@[\w\.-]+\.[A-Za-z]{2,}$", val):
                errors[fid] = "Must be a valid email address."
        elif rule == "phone_number":
            if not re.fullmatch(r"\d{11}", val):
                errors[fid] = "Must be exactly 11 digits."
        
        # ─── INSERT NEW “rule” HANDLERS HERE ───────────────────────────────────────
        elif rule == "credit_card_format":
            # simple Luhn‐like or digit‐count check:
            if not re.fullmatch(r"\d{13,19}", val.replace(" ", "")):
                errors[fid] = "Must be 13–19 digits (spaces allowed)."
        elif rule == "expiry_format":
            # MM/YY between 01/23–12/50, for instance
            m = re.fullmatch(r"(0[1-9]|1[0-2])\/([2-9]\d)", val)
            if not m:
                errors[fid] = "Must be in MM/YY format."
        elif rule == "national_id":
            # e.g. Pakistani CNIC: 5-7 digits, dash, 7 digits, dash, 1 digit
            if not re.fullmatch(r"\d{5}-\d{7}-\d", val):
                errors[fid] = "Invalid National ID format."
        elif rule == "alphanumeric":
            if not re.fullmatch(r"[A-Za-z0-9]+", val):
                errors[fid] = "Only letters and numbers allowed."
        elif rule == "available_username":
            # placeholder for async check
            # you’d normally call your user‐service here
            if val.lower() in ("admin","test","root"):
                errors[fid] = "Username is already taken."
        elif rule == "captcha":
            # CAPTCHA rule present, but no validation is applied
            pass

        
         # 6) Cross-field logic (e.g., confirm password)
        if "PASSWORD" in values and "CONFIRM_PASSWORD" in values:
            if values["PASSWORD"] != values["CONFIRM_PASSWORD"]:
                errors["CONFIRM_PASSWORD"] = "Passwords do not match."

        # 7) Type parsing for number/date
        if field.get("type") == "number":
            try:
                float(val)  # or int(val), depending on your expected precision
            except ValueError:
                errors[fid] = "Must be a valid number."
        elif field.get("type") == "date":
            try:
                from datetime import datetime
                datetime.strptime(val, "%Y-%m-%d")  # adjust format as needed
            except ValueError:
                errors[fid] = "Must be a valid date (YYYY-MM-DD)."
        
        # ─── after your numeric/date parsing block ─────────────────────────────────
        # handle date_range pickers:
        if field.get("type") == "date_range" and val:
            # expect JSON string: {"start":"YYYY-MM-DD","end":"YYYY-MM-DD"}
            try:
                jr = json.loads(val)
                from datetime import datetime
                s = datetime.strptime(jr["start"], "%Y-%m-%d")
                e = datetime.strptime(jr["end"],   "%Y-%m-%d")
                if e < s:
                    errors[fid] = "End date must be on or after start date."
            except Exception:
                errors[fid] = "Invalid date range format."
        
        # enforce tag limits:
        if field.get("type") == "tags":
            tags = [t.strip() for t in val.split(",") if t.strip()]
            max_tags = rules.get("maxTags")
            if max_tags and len(tags) > max_tags:
                errors[fid] = f"Select no more than {max_tags} tags."

        # enforce star‐rating bounds:
        if field.get("type") == "rating" and val:
            try:
                r = int(val)
                mn, mx = rules.get("min",1), rules.get("max",5)
                if r < mn or r > mx:
                    errors[fid] = f"Rating must be between {mn} and {mx}."
            except ValueError:
                errors[fid] = "Rating must be a number."

        # timezone validation:
        if field.get("type") == "select" and fid == "TIMEZONE" and val:
            if val not in pytz.all_timezones:
                errors[fid] = "Invalid timezone selected."
        
        # 8) Range limits
        if field.get("type") == "number":
            try:
                num_val = float(val)
                if "min" in rules and num_val < rules["min"]:
                    errors[fid] = f"Value must be at least {rules['min']}."
                if "max" in rules and num_val > rules["max"]:
                    errors[fid] = f"Value must be at most {rules['max']}."
            except ValueError:
                pass

        # 9) Enum enforcement (select field must match allowed options)
        allowed_options = rules.get("options") or field.get("options")
        if field.get("type") == "select" and allowed_options:
            if val not in allowed_options:
                errors[fid] = f"Invalid option selected. Choose from: {', '.join(allowed_options)}"
        
        # 10) Basic sanitization check (e.g., disallow HTML tags)
        if re.search(r"<[^>]+>", val):
            errors[fid] = "HTML tags are not allowed."

    return errors


@app.route("/submit", methods=["POST"])
@limiter.limit("5 per minute")
def submit_route():
    payload = request.get_json(force=True)
    values  = payload.get("values", {})
    schema  = payload.get("schema", [])

    # debug log—remove or comment out in production
    print(">>> /submit values:", values)
    print(">>> /submit schema:", [f['id'] + ":" + str(f.get('validation')) for f in schema])

    errs = validate_submission(values, schema)
    if errs:
        return jsonify({"success": False, "errors": errs}), 400

    # All validations passed—proceed with your next steps
    return jsonify({"success": True, "message": "Form submitted successfully."})
if __name__ == "__main__":
    app.run(debug=True)