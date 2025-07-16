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

        self.template_keywords = {}
        for template_id, template_data in self.form_templates.items():
            if isinstance(template_data, dict):
                # The template's name itself is a keyword (e.g., "job_application" -> "job application")
                self.template_keywords[template_id.replace('_', ' ')] = template_id
                # Add all seeds from the JSON file
                for seed in template_data.get("seeds", []):
                    self.template_keywords[seed.lower()] = template_id

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
        # --- ADD THIS LINE ---
        matcher.add("ATTR_OPTIONAL", [
            [{"LOWER": "optional"}], 
            [{"LOWER": "not"}, {"LOWER": "required"}]
        ])
        # --- END ADDITION ---
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not", "don't", "no"]}}]])
        matcher.add("SMART_QUANTIFIER", [
    [
        {"like_num": True}, # e.g., "five"
        {"OP": "*", "is_punct": False}, # Optional words in between
        # The target can be a generic type OR a specific noun
        {"LOWER": {"IN": [
            "text", "number", "date", "file", "url", "checkbox", "radio", # Generic types
            "reference", "references", "comment", "comments", "question", "questions" # Specific, quantifiable nouns
            # Add any other specific nouns you want to be quantifiable here
        ]}}
    ]
])
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
        doc = nlp(prompt)
        all_matches = self.matcher(doc)
        all_matches = self.filter_overlapping_matches(all_matches)

        # --- Phase 1: Intent Extraction ---
        excluded_ids, quantities, attributes, explicit_ids = set(), {}, [], set()
        dynamic_ranges, dynamic_options, generic_fields = [], [], []

        # This loop now correctly identifies all intents before any fields are generated.
        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]

            if rule_id.startswith("GEN_"):
                num_text = doc[start].text
                num = self.word_to_num(num_text) or (int(num_text) if num_text.isdigit() else 1)
                field_type = rule_id.split('_')[1].lower()
                generic_fields.append({"type": field_type, "count": num})
            
            elif rule_id == "LOGIC_OPTIONS":
                subject_end_token_index = next((i for i in range(start, end) if doc[i].lower_ == "with"), None)
                if not subject_end_token_index: continue
                subject_phrase = doc[start:subject_end_token_index].text
                options_text_span = doc[end:]
                options_list = [opt.strip().replace("'", "").title() for part in options_text_span.text.split(' and ') for opt in part.split(',') if opt.strip()]
                final_options = [opt for opt in options_list if not any(verb in opt.lower() for verb in [' is ', ' are ', ' make ', ' add '])]
                if subject_phrase and final_options:
                    dynamic_options.append({"subject": subject_phrase, "options": final_options})

            elif rule_id == "LOGIC_NUMERIC_RANGE":
                nums = [int(token.text) for token in doc[start:end] if token.like_num]
                if len(nums) == 2:
                    dynamic_ranges.append({"min": min(nums), "max": max(nums), "pos": start})

            elif rule_id == "LOGIC_NEGATION":
                window = doc[end : end + 5]
                for n in range(1, 4):
                    for i in range(len(window) - n + 1):
                        phrase = window[i : i+n].text.lower()
                        target_match = process.extractOne(phrase, self.fuzzy_map.keys(), score_cutoff=90)
                        if target_match:
                            excluded_ids.add(self.fuzzy_map[target_match[0]])

            elif rule_id == "LOGIC_QUANTIFIER":
                num_text = doc[start].text
                num = self.word_to_num(num_text) or (int(num_text) if num_text.isdigit() else None)
                target_noun_phrase = doc[start+1:end].text
                if num:
                    target_match = process.extractOne(target_noun_phrase, self.fuzzy_map.keys(), score_cutoff=85)
                    if target_match:
                        quantities[self.fuzzy_map[target_match[0]]] = {"num": num, "pos": start}

            elif rule_id.startswith("ATTR_"):
                attributes.append({"rule": rule_id, "pos": start})
            
            elif rule_id in self.field_map:
                explicit_ids.add((rule_id, start))

        # --- Phase 2: Field Generation ---
        candidate_fields, added_ids = [], set()
        detected_template_name = "custom"

        def create_field_entry(field_def, source, confidence, pos=None):
            entry = { "id": field_def.id, "label": field_def.label, "type": field_def.type, "source": source, "confidence": confidence, "validation": dict(field_def.validation) }
            if pos is not None: entry['pos'] = pos
            return entry

        # Step 2.1: Process HIGH-PRIORITY Generic Field Requests
        has_generic_requests = len(generic_fields) > 0
        if has_generic_requests:
            for req in generic_fields:
                for i in range(req['count']):
                    field_type = req['type']
                    generic_field_data = { "id": f"GENERIC_{field_type.upper()}_{i+1}", "label": f"{field_type.title()} Field #{i+1}", "type": field_type, "validation": {} }
                    new_field = create_field_entry(FieldDefinition(**generic_field_data), "generic_request", 1.0)
                    candidate_fields.append(new_field)
                    added_ids.add(new_field['id'])

        # Step 2.2: Template Detection (conditional)
        if not has_generic_requests:
            prompt_lower = prompt.lower()
            best_match = process.extractOne(prompt_lower, self.template_keywords.keys(), score_cutoff=88)
            if best_match:
                template_id = self.template_keywords[best_match[0]]
                template_data = self.form_templates[template_id]
                template_field_ids = template_data.get("fields", [])
                detected_template_name = template_id
            else:
                template_field_ids = []

            # Process Template Fields
            for item in template_field_ids:
                field_id = item['id'] if isinstance(item, dict) else item
                if field_id not in added_ids and field_id not in excluded_ids:
                    template_overrides = item.get('validation', {}) if isinstance(item, dict) else {}
                    field_def = self.field_map[field_id]
                    new_field = create_field_entry(field_def, "template", 0.90)
                    new_field['validation'].update(template_overrides)
                    candidate_fields.append(new_field)
                    added_ids.add(field_id)

        # Step 2.3: Assemble remaining fields (Specific Quantifiers and Explicit Matches)
        for field_id, data in quantities.items():
            if field_id in added_ids or field_id in excluded_ids: continue
            field_def = self.field_map[field_id]
            for i in range(data['num']):
                entry = create_field_entry(field_def, "quantifier", 0.95, data['pos'])
                entry['label'] = f"{field_def.label} #{i+1}"
                candidate_fields.append(entry)
            added_ids.add(field_id)

        for field_id, pos in explicit_ids:
            if field_id not in added_ids and field_id not in excluded_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append(create_field_entry(field_def, "matcher", 1.0, pos))
                added_ids.add(field_id)

        # --- Phase 3: Filtering & Attribute Application ---
        final_fields = candidate_fields
        for attr in attributes:
            fields_with_pos = [f for f in final_fields if 'pos' in f]
            if not fields_with_pos: continue
            target_field = min(fields_with_pos, key=lambda f: abs(f['pos'] - attr['pos']))
            is_quantifier = target_field.get('source') == 'quantifier'
            fields_to_modify = [f for f in final_fields if f['id'] == target_field['id'] and f.get('source') == 'quantifier'] if is_quantifier else [target_field]
            for field in fields_to_modify:
                if attr['rule'] == 'ATTR_REQUIRED': field['validation']['required'] = True
                elif attr['rule'] == 'ATTR_OPTIONAL': field['validation']['required'] = False
        
        for drange in dynamic_ranges:
            applicable_fields = [f for f in final_fields if f.get('type') in ['number', 'range'] and 'pos' in f]
            if not applicable_fields and "RATING" in self.field_map:
                rating_field = create_field_entry(self.field_map["RATING"], "logic_range", 0.95, drange['pos'])
                final_fields.append(rating_field)
                applicable_fields.append(rating_field)
            if applicable_fields:
                target_field = min(applicable_fields, key=lambda f: abs(f['pos'] - drange['pos']))
                target_field['validation']['min'] = drange['min']
                target_field['validation']['max'] = drange['max']
                target_field['type'] = 'range'
                target_field['label'] = f"{target_field['label']} ({drange['min']}-{drange['max']})"

        for d_opts in dynamic_options:
            subject, options = d_opts["subject"], d_opts["options"]
            candidate_field_map = {f['label'].lower(): f for f in final_fields}
            target_match = process.extractOne(subject, candidate_field_map.keys(), score_cutoff=85)
            if target_match:
                target_field = candidate_field_map[target_match[0]]
                target_field['options'] = options
                target_field['type'] = 'select'
            else:
                arbitrary_field = { "id": subject.upper().replace(" ", "_"), "label": subject.title(), "type": "select", "source": "arbitrary_options", "confidence": 0.90, "options": options, "validation": {} }
                final_fields.append(arbitrary_field)

        # --- Phase 4: Post-Processing and Cleanup ---
        final_fields = self.post_process_name_fields(final_fields)
        for field in final_fields:
            field.pop('pos', None)

        password_field_index = next((i for i, field in enumerate(final_fields) if field.get('id') == 'PASSWORD'), -1)
        if password_field_index != -1 and "CONFIRM_PASSWORD" not in added_ids:
            if re.search(r"\b(confirm|confirmation|retype).{0,5}password", prompt.lower()):
                confirm_password_field = create_field_entry(self.field_map["CONFIRM_PASSWORD"], "logic", 0.98)
                final_fields.insert(password_field_index + 1, confirm_password_field)

        type_defaults = { "textarea": {"required": False, "maxLength": 1000}, "text": {"required": False, "maxLength": 255}, "file": {"required": False}, "url": {"required": False, "rule": "url"}, "email": {"required": True, "pattern": r'^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$'}, "tel": {"required": False, "pattern": r'^\d{10,15}$'}, "date": {"required": False}, "time": {"required": False}, "select": {"required": False}, "radio": {"required": False}, "checkbox": {"required": False}, "number": {"required": False}, "range": {"required": False}, "password": {"required": True, "minLength": 8} }
        for field in final_fields:
            val = field.setdefault("validation", {})
            defaults = type_defaults.get(field["type"], {})
            for key, default_val in defaults.items():
                val.setdefault(key, default_val)
            if field.get('id') in ('FIRST_NAME', 'LAST_NAME', 'FULL_NAME'):
                val.setdefault('required', True)

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
    
    # ─── Step 0: Basic Prompt Quality Check ────────────────────────────────
    cleaned = prompt.strip()
    word_count = len(cleaned.split())

    # Reject if too short, too few words, digits only, or trivial words
    if (
        len(cleaned) < 10 or
        word_count < 3 or
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