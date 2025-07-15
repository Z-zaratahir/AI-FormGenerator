from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import spacy
from spacy.matcher import Matcher
#from spacy.tokens import Span
#from spacy.util import filter_spans
from rapidfuzz import process
import re
import json

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
    def __init__(self, id, label, type, patterns, fuzzy_keywords=None, validation=None, **kwargs):
        self.id = id
        self.label = label
        self.type = type
        self.patterns = patterns
        self.fuzzy_keywords = fuzzy_keywords or []
        self.validation = validation or {}

# --- The Form Generator Engine ---
class FormGenerator:
    def __init__(self, fields_data, templates_data):
        field_definitions = [FieldDefinition(**data) for data in fields_data]
        self.field_map = {f.id: f for f in field_definitions}
        self.fuzzy_map = {kw: f.id for f in field_definitions for kw in f.fuzzy_keywords}
        for field in field_definitions:
            self.fuzzy_map[field.label.lower()] = field.id
            
        self.matcher = self._build_matcher(field_definitions)
        self.form_templates = self._resolve_template_aliases(templates_data)

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

    def _build_matcher(self, field_definitions):
        matcher = Matcher(nlp.vocab)
        for field in field_definitions:
            matcher.add(field.id, field.patterns)

        # Attribute & Logic Patterns
        matcher.add("ATTR_REQUIRED", [[{"LOWER": "required"}]])
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not", "don't", "no"]}}]])
        matcher.add("LOGIC_QUANTIFIER", [[{"like_num": True}, {"OP": "*"}, {"POS": "NOUN"}]])
        matcher.add("LOGIC_NUMERIC_RANGE", [
            [{"like_num": True}, {"ORTH": "-", "OP": "?"}, {"like_num": True}], # "1-10" or "1 10"
            [{"like_num": True}, {"LOWER": "to"}, {"like_num": True}]           # "1 to 10"
        ])
        matcher.add("LOGIC_OPTIONS", [
        [
            {"POS": "NOUN", "OP": "+"}, # One or more nouns (e.g., "satisfaction level")
            {"LOWER": "with"},
            {"LOWER": {"IN": ["options", "choices"]}},
            {"LOWER": {"IN": ["for", "of"]}, "OP": "?"} # Optional "for" or "of"
        ]
    ])
        return matcher
    
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
        doc = nlp(prompt)
        all_matches = self.matcher(doc)
        


        # --- Phase 1: Intent Extraction ---
        excluded_ids, quantities, attributes, explicit_ids = set(), {}, [], set()
        dynamic_ranges = [] # For storing extracted ranges like "1-10"
        dynamic_options = []

        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]

            if rule_id == "LOGIC_OPTIONS":
                # The 'end' is the token where the trigger phrase (e.g., "with options") ends.
                # Find the token index for "with" to separate the subject from the trigger.
                subject_end_token_index = next((i for i in range(start, end) if doc[i].lower_ == "with"), None)
                if not subject_end_token_index: continue

                # The subject is the noun phrase before "with".
                subject_phrase = doc[start:subject_end_token_index].text
                
                # The options list starts after the matched pattern.
                options_text_span = doc[end:]
                
                # Logic to parse the options string into a clean list
                options_list = []
                for part in options_text_span.text.split(' and '):
                    options_list.extend(part.split(','))
                
                cleaned_options = [opt.strip().replace("'", "").title() for opt in options_list if opt.strip()]
                
                # Stop parsing if we hit a verb, indicating a new clause.
                final_options = []
                for option in cleaned_options:
                    if any(verb in option.lower() for verb in [' is ', ' are ', ' make ', ' add ']):
                        break
                    final_options.append(option)
                
                if subject_phrase and final_options:
                    dynamic_options.append({"subject": subject_phrase, "options": final_options})

            elif rule_id == "LOGIC_NUMERIC_RANGE":
                span = doc[start:end]
                nums = [int(token.text) for token in span if token.like_num]
                if len(nums) == 2:
                    dynamic_ranges.append({"min": min(nums), "max": max(nums), "pos": start})
            
            elif rule_id == "LOGIC_NEGATION":
                negated_nouns = self.find_all_negated_nouns(doc, end)
                for noun in negated_nouns:
                    target_match = process.extractOne(noun, self.fuzzy_map.keys())
                    if target_match and target_match[1] > 80:
                        excluded_ids.add(self.fuzzy_map[target_match[0]])
            
            elif rule_id == "LOGIC_QUANTIFIER":
                num_text = doc[start].text
                num = self.word_to_num(num_text) or (int(num_text) if num_text.isdigit() else None)
                target_noun_phrase = doc[start+1:end].text
                if num:
                    target_match = process.extractOne(target_noun_phrase, self.fuzzy_map.keys())
                    if target_match and target_match[1] > 80:
                        quantities[self.fuzzy_map[target_match[0]]] = {"num": num, "pos": start}
            
            elif rule_id.startswith("ATTR_"):
                attributes.append({"rule": rule_id, "pos": start})
            
            elif rule_id in self.field_map:
                explicit_ids.add((rule_id, start))


        # --- Phase 2: Field Generation ---
        candidate_fields, added_ids = [], set()
        detected_template_name = "custom"

        def create_field_entry(field_def, source, confidence, pos=None):
            """Helper to create a new field dictionary, including a deep copy of validation rules."""
            entry = {
                "id": field_def.id,
                "label": field_def.label,
                "type": field_def.type,
                "source": source,
                "confidence": confidence,
                "validation": dict(field_def.validation) # Use dict() for a shallow copy, sufficient for a 1-level dict.
            }
            if pos is not None:
                entry['pos'] = pos
            return entry

        # Step 1: Template Detection
        prompt_lower = prompt.lower()
        sorted_keys = sorted([k for k,v in self.form_templates.items() if isinstance(v, dict)], key=len, reverse=True)
        for key in sorted_keys:
            template_data = self.form_templates[key]
            search_terms = [key.replace('_', ' ')] + template_data.get('seeds', [])
            if any(re.search(r'\b' + re.escape(term) + r'\b', prompt_lower) for term in search_terms):
                template_field_ids = template_data.get("fields", [])
                detected_template_name = key
                break
        else:
            template_field_ids = []

        # Step 2: Assemble fields (Quantifiers > Explicit > Template)
        # Process Quantifiers
        for field_id, data in quantities.items():
            if field_id in excluded_ids: continue
            field_def = self.field_map[field_id]
            for i in range(data['num']):
                # Use the new helper function to create each field instance
                entry = create_field_entry(field_def, "quantifier", 0.95, data['pos'])
                entry['label'] = f"{field_def.label} #{i+1}" # Customize label for quantifiers
                candidate_fields.append(entry)
            added_ids.add(field_id)

        # Process Explicit Matches
        for field_id, pos in explicit_ids:
            if field_id not in added_ids and field_id not in excluded_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append(create_field_entry(field_def, "matcher", 1.0, pos))
                added_ids.add(field_id)

        # Process Template Fields
        for field_id in template_field_ids:
            if field_id not in added_ids and field_id not in excluded_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append(create_field_entry(field_def, "template", 0.90))
                added_ids.add(field_id)



        # --- Phase 3: Filtering & Attribute Application ---
        final_fields = candidate_fields 

        # Apply Attributes (e.g., "required")
        for attr in attributes:
            fields_with_pos = [f for f in final_fields if 'pos' in f]
            if not fields_with_pos: continue
            target_field = min(fields_with_pos, key=lambda f: abs(f['pos'] - attr['pos']))
            if attr['rule'] == "ATTR_REQUIRED":
                if target_field.get('source') == 'quantifier':
                    for field in final_fields:
                        target_field['validation']['required'] = True
        
        # Apply Dynamic Ranges
        for drange in dynamic_ranges:
            applicable_fields = [f for f in final_fields if f.get('type') == 'number' and 'pos' in f]
            if not applicable_fields: continue
            target_field = min(applicable_fields, key=lambda f: abs(f['pos'] - drange['pos']))
            target_field['validation']['min'] = drange['min']
            target_field['validation']['max'] = drange['max']
            target_field['type'] = 'range'
            target_field['label'] = f"Rating ({drange['min']}-{drange['max']})"

        # Dynamic Options based on subject, not proximity
        for d_opts in dynamic_options:
            subject = d_opts["subject"]
            options = d_opts["options"]
            
            candidate_field_map = {f['label'].lower(): f for f in final_fields}
            target_match = process.extractOne(subject, candidate_field_map.keys(), score_cutoff=85)
            
            if target_match:
                target_field = candidate_field_map[target_match[0]]
                target_field['options'] = options
                target_field['type'] = 'select'
            else:
                # Graceful Fallback: Create a new field if no existing one matches the subject
                arbitrary_field = {
                    "id": subject.upper().replace(" ", "_"), "label": subject.title(),
                    "type": "select", "source": "arbitrary_options", "confidence": 0.90,
                    "options": options, "validation": {}
                }
                final_fields.append(arbitrary_field)


        # --- Phase 4: Post-Processing and Cleanup ---
        # --- Phase 4: Post-Processing and Cleanup ---
        final_fields = self.post_process_name_fields(final_fields)

        # strip out internal 'pos' tags
        for field in final_fields: 
            field.pop('pos', None)

        # password‐confirmation logic unchanged...
        password_field_index = next((i for i, field in enumerate(final_fields) if field.get('id') == 'PASSWORD'), -1)
        if password_field_index != -1 and "CONFIRM_PASSWORD" not in added_ids:
            if re.search(r"\b(confirm|confirmation|retype).{0,5}password", prompt.lower()):
                field_def = self.field_map["CONFIRM_PASSWORD"]
                confirm_password_field = create_field_entry(field_def, "logic", 0.98)
                final_fields.insert(password_field_index + 1, confirm_password_field)

        # ─── New: Field-specific regex validations ────────────────────────────────────
        for field in final_fields:
            fid = field.get('id', '')
            # Email: must contain '@' and end with '.com'
            if fid == 'EMAIL':
                field['validation'].update({
                    'required': True,
                    'pattern': r'^[\w\.-]+@[\w\.-]+\.[cC][oO][m]$'
                })
            # Phone: exactly 11 digits
            elif fid == 'PHONE':
                field['validation'].update({
                    'required': True,
                    'pattern': r'^\d{11}$'
                })
            # Name fields: cannot be empty
            elif fid in ('FIRST_NAME', 'LAST_NAME', 'FULL_NAME'):
                field['validation'].update({
                    'required': True
                })
            # You can extend this `elif` chain for any other special fields.
        
        # ─── Step 0: (Optional) Your existing per‑ID overrides ──────────────────────
        # (You can leave your EMAIL, PHONE, NAME regex blocks here)

        # ─── Step 1: Define generic defaults per field type ────────────────────────
        type_defaults = {
            "textarea": {"required": False, "maxLength": 1000},
            "text":     {"required": False, "maxLength": 255},
            "file":     {"required": False},   # most file fields define their own fileTypes/maxSize in JSON
            "url":      {"required": False, "rule": "url"},
            "email":    {"required": True,  "rule": "email_format"},
            "tel":      {"required": True,  "pattern": r"^\d{11}$"},
            "date":     {"required": False},
            "time":     {"required": False},
            "select":   {"required": False},
            "radio":    {"required": False},
            "checkbox": {"required": False},
            "number":   {"required": False},
            "password": {"required": True,  "minLength": 8}
            # add any other types you want as catch‑alls…
        }

        # ─── Step 2: Merge JSON + per‑ID + type defaults ───────────────────────────
        for field in final_fields:
            # 1) Start with whatever came from fields.json
            val = field.setdefault("validation", {})

            # 2) (Optional) Your per‑ID overrides—e.g. EMAIL, PHONE, NAME—go here
            #    (skip this if you prefer to drive everything from JSON + type_defaults)

            # 3) Fill in any missing keys from the type_defaults map
            defaults = type_defaults.get(field["type"], {})
            for key, default_val in defaults.items():
                val.setdefault(key, default_val)


        return final_fields, detected_template_name


# --- Main Application Setup ---
fields_data, templates_data = load_knowledge_base('fields.json', 'templates.json')
form_gen = FormGenerator(fields_data, templates_data)

@app.route("/process", methods=["POST"])
@limiter.limit("2 per second")
def process_prompt_route():
    data = request.get_json()
    if not data or not (prompt := data.get("prompt")):
        return jsonify({"error": "Prompt is empty or invalid request"}), 400
    
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