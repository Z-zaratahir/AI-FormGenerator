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
            if field.patterns:
                matcher.add(field.id, field.patterns)

        # These patterns handle all common ways of expressing obligation.
        matcher.add("ATTR_REQUIRED", [
            [{"LOWER": "required"}], [{"LOWER": "mandatory"}], [{"LOWER": "compulsory"}], [{"LOWER": "essential"}],
            [{"LOWER": "must"}, {"LEMMA": "be"}], [{"LOWER": "has"}, {"LOWER": "to"}, {"LEMMA": "be"}],
            [{"LEMMA": "need"}, {"LOWER": "to"}, {"LEMMA": "be"}],
            [{"LOWER": "not"}, {"LEMMA": "be", "OP": "?"}, {"LOWER": "optional"}],
            [{"LEMMA": "be"}, {"LOWER": "not"}, {"LOWER": "optional"}],
            [{"LOWER": "cannot"}, {"LEMMA": "be"}, {"LOWER": "skipped"}],
            [{"LOWER": "can"}, {"LOWER": "n't"}, {"LEMMA": "be"}, {"LOWER": "skipped"}],
        ])
        matcher.add("ATTR_OPTIONAL", [
            [{"LOWER": "optional"}],
            [{"LOWER": "not"}, {"LEMMA": "be", "OP": "?"}, {"LOWER": "required"}],
            [{"LEMMA": "be"}, {"LOWER": "not"}, {"LOWER": "required"}],
            [{"LOWER": "not"}, {"LOWER": "mandatory"}],
            [{"LEMMA": "can"}, {"LEMMA": "be"}, {"LOWER": "skipped"}],
            [{"LOWER": "doesn't"}, {"LOWER": "have"}, {"LOWER": "to"}, {"LOWER": "be"}],
        ])
        matcher.add("ATTR_GLOBAL_ALL", [
            [{"LOWER": "all"}, {"LOWER": "fields"}],
            [{"LOWER": "every"}, {"LOWER": "field"}],
        ])
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not", "don't", "no"]}}]])
        
        # This is the single, unified quantifier rule that handles both generic and specific nouns
        matcher.add("SMART_QUANTIFIER", [[
            {"like_num": True},
            {"POS": {"IN": ["ADJ", "NOUN"]}, "OP": "*"}, # Allow adjectives or nouns in between
            {"LOWER": {"IN": [
                "text", "number", "date", "file", "url", "checkbox", "radio", "textarea",
                "reference", "references", "comment", "comments", "question", "questions", "option", "options"
            ]}}
        ]])
        
        matcher.add("LOGIC_NUMERIC_RANGE", [[{"like_num": True}, {"ORTH": "-", "OP": "?"}, {"like_num": True}], [{"like_num": True}, {"LOWER": "to"}, {"like_num": True}]])
        matcher.add("LOGIC_OPTIONS", [[{"POS": "NOUN", "OP": "+"}, {"LOWER": "with"}, {"LOWER": {"IN": ["options", "choices"]}}, {"LOWER": {"IN": ["for", "of"]}, "OP": "?"}]])
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
        attributes, quantities, dynamic_options, dynamic_ranges = [], {}, [], []
        explicit_ids, excluded_ids, exception_ids = set(), set(), set()
        global_attribute = None
        
        processed_token_indices = set()

        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]
            span = doc[start:end]
            processed_token_indices.update(range(start, end))

            if rule_id.startswith("ATTR_"):
                # Check for global attributes first
                if rule_id == "ATTR_GLOBAL_ALL":
                    # Find the actual attribute that follows, e.g., "all fields REQUIRED"
                    following_token = doc[end] if end < len(doc) else None
                    if following_token and following_token.lower_ == "required":
                        global_attribute = "ATTR_REQUIRED"
                    # Add more global checks if needed
                else:
                    attributes.append({"rule": rule_id, "pos": start, "span": span})

            elif rule_id == "LOGIC_NEGATION" and span.text.lower() == "except":
                # Find the noun following "except" to create an exception
                for i in range(end, min(end + 4, len(doc))):
                    token = doc[i]
                    if token.pos_ == 'NOUN':
                        target_match = process.extractOne(token.lemma_, self.fuzzy_map.keys(), score_cutoff=85)
                        if target_match:
                            exception_ids.add(self.fuzzy_map[target_match[0]])
                        break # Found the noun, stop searching

            elif rule_id == "SMART_QUANTIFIER":
                span = doc[start:end]
                num_token = span[0]
                num = self.word_to_num(num_token.text) or (int(num_token.text) if num_token.like_num else 1)
                
                keyword_token = None
                quantifier_keywords = {
                    "text", "number", "date", "file", "url", "checkbox", "radio", "textarea",
                    "reference", "references", "comment", "comments", "question", "questions", "option", "options"
                }
                for token in span:
                    if token.lower_ in quantifier_keywords:
                        keyword_token = token
                        break
                
                if keyword_token:
                    keyword = keyword_token.lemma_.lower()
                    # STEP 1: Store the full match range (start, end) not just the position.
                    quantities[keyword] = {"num": num, "start": start, "end": end}

            elif rule_id in self.field_map:
                explicit_ids.add((rule_id, start))
            elif rule_id == "LOGIC_NEGATION":
                window = doc[end: end + 5]
                for n in range(1, 4):
                    for i in range(len(window) - n + 1):
                        phrase = window[i: i + n].text.lower()
                        target_match = process.extractOne(phrase, self.fuzzy_map.keys(), score_cutoff=90)
                        if target_match:
                            excluded_ids.add(self.fuzzy_map[target_match[0]])
            elif rule_id in self.field_map:
                explicit_ids.add((rule_id, start))
            elif rule_id == "LOGIC_NUMERIC_RANGE":
                nums = [int(token.text) for token in doc[start:end] if token.like_num]
                if len(nums) == 2:
                    dynamic_ranges.append({"min": min(nums), "max": max(nums), "pos": start})
            elif rule_id.startswith("ATTR_"):
                attributes.append({"rule": rule_id, "pos": start})
            elif rule_id == "LOGIC_OPTIONS":
                subject_end_token_index = next((i for i in range(start, end) if doc[i].lower_ == "with"), None)
                if not subject_end_token_index:
                    continue
                subject_phrase = doc[start:subject_end_token_index].text
                options_text_span = doc[end:]
                options_list = [opt.strip().replace("'", "").title() for part in options_text_span.text.split(' and ') for opt in part.split(',') if opt.strip()]
                final_options = [opt for opt in options_list if not any(verb in opt.lower() for verb in [' is ', ' are ', ' make ', ' add '])]
                if subject_phrase and final_options:
                    dynamic_options.append({"subject": subject_phrase, "options": final_options})

        # --- Phase 2: Field Generation ---

        def create_field_entry(field_def, source, confidence, pos=None):
            entry = {
                "id": field_def.id,
                "label": field_def.label,
                "type": field_def.type,
                "source": source,
                "confidence": confidence,
                "validation": dict(field_def.validation),
                "options": field_def.options  # <-- This line was missing
            }
            if pos is not None:
                entry['pos'] = pos
            return entry

        final_fields_map = {}

        # Step 1: Template Detection (Highest Priority)
        prompt_lower = prompt.lower()
        detected_template_name = "custom"
        best_match_score = 0
        best_template_id = None

        for template_name, data in self.form_templates.items():
            # Create a list of all possible keywords for this template
            all_seeds = [template_name.replace('_', ' ')]
            if isinstance(data, dict) and "seeds" in data:
                all_seeds.extend(data.get("seeds", []))

            # Check if any seed word is present in the prompt
            for seed in all_seeds:
                if seed in prompt_lower:
                    # Prioritize longer, more specific matches
                    score = 90 + len(seed)
                    if score > best_match_score:
                        best_match_score = score
                        best_template_id = template_name

        if best_template_id:
            detected_template_name = best_template_id
            template_data = self.form_templates.get(best_template_id, {})
            # Resolve aliases (e.g., "application" -> "job_application")
            while isinstance(template_data, str):
                template_data = self.form_templates.get(template_data, {})

            template_field_ids = template_data.get("fields", [])
            for item in template_field_ids:
                field_id = item.get('id') if isinstance(item, dict) else item
                if field_id not in excluded_ids and self.field_map.get(field_id):
                    overrides = item.get('validation', {}) if isinstance(item, dict) else {}
                    field_def = self.field_map[field_id]
                    new_field = create_field_entry(field_def, "template", 0.90)
                    new_field['validation'].update(overrides)
                    final_fields_map[field_id] = new_field

        # Step 1.5: Handle Dynamic Options to claim their subjects before generic quantifiers
        subjects_handled_by_dynamic_options = set()
        for i, dopt in enumerate(dynamic_options):
            field_id = f"DYNAMIC_SELECT_{i+1}"
            dynamic_field_def = FieldDefinition(
                id=field_id,
                label=dopt['subject'].title(),
                type='select',
                options=dopt['options']
            )
            final_fields_map[field_id] = create_field_entry(dynamic_field_def, "dynamic_options", 1.0)
            if dopt['subject']:
                last_word = dopt['subject'].split()[-1].lower()
                singular_word = last_word.rstrip('s')
                subjects_handled_by_dynamic_options.add(singular_word)
                subjects_handled_by_dynamic_options.add(f"{singular_word}s")
                # Also add the word 'option' to the set since it triggered this
                subjects_handled_by_dynamic_options.add("option")
                subjects_handled_by_dynamic_options.add("options")


        # Step 2: Process Quantifiers (High Priority)
        generic_types = ["text", "number", "date", "file", "url", "checkbox", "radio", "textarea", "option"]
        quantified_field_ids = set()

        for keyword, data in quantities.items():
            if keyword in subjects_handled_by_dynamic_options:
                continue

            # STEP 2: Be PRECISE. Only mark the tokens of this specific match as processed.
            processed_token_indices.update(range(data['start'], data['end']))

            if keyword in generic_types:
                for i in range(data['num']):
                    field_id = f"GENERIC_{keyword.upper()}_{i+1}"
                    field_type = 'checkbox' if keyword == 'option' else keyword
                    generic_def = FieldDefinition(id=field_id, label=f"{keyword.title()} Field #{i+1}", type=field_type)
                    # Use 'start' instead of 'pos' for consistency
                    final_fields_map[field_id] = create_field_entry(generic_def, "generic_quantifier", 1.0, data['start'])
            else:
                target_match = process.extractOne(keyword, self.fuzzy_map.keys(), score_cutoff=88)
                if target_match:
                    field_id_base = self.fuzzy_map[target_match[0]]
                    if field_id_base in self.field_map:
                        quantified_field_ids.add(field_id_base)
                        final_fields_map.pop(field_id_base, None)
                        
                        for i in range(data['num']):
                            entry_id = f"{field_id_base}_{i+1}"
                            entry_label = f"{self.field_map[field_id_base].label} #{i+1}"
                            
                            copied_def = copy.deepcopy(self.field_map[field_id_base])
                            copied_def.id = entry_id
                            copied_def.label = entry_label
                            
                            # Use 'start' instead of 'pos' for consistency
                            final_fields_map[entry_id] = create_field_entry(copied_def, "quantifier", 0.95, data['start'])
        
        # Step 3: Add other explicitly mentioned fields (from specific matcher patterns)
        for field_id, pos in explicit_ids:
            if field_id not in final_fields_map and field_id not in excluded_ids:
                final_fields_map[field_id] = create_field_entry(self.field_map[field_id], "matcher", 1.0, pos)

        # Step 4: Intelligent Noun Chunk Fallback Scan
        if not best_template_id:
            for chunk in doc.noun_chunks:
                if any(token.i in processed_token_indices for token in chunk):
                    continue

                target_match = process.extractOne(chunk.lemma_, self.fuzzy_map.keys(), score_cutoff=88)
                if target_match:
                    field_id = self.fuzzy_map[target_match[0]]
                    if field_id in quantified_field_ids:
                        continue
                    
                    if field_id not in final_fields_map and field_id in self.field_map:
                        final_fields_map[field_id] = create_field_entry(self.field_map[field_id], "noun_chunk_scan", 0.85, chunk.start)
                        processed_token_indices.update(range(chunk.start, chunk.end))

        # The final list of fields is the values from our map
        final_fields = list(final_fields_map.values())


        # --- Phase 3 & 4: Cleanup and Attribute Application ---

        # Step A: Apply all base and default validations FIRST.
        # This sets a baseline for every field.
        for field in final_fields:
            val = field.setdefault("validation", {})
            
            type_defaults = {
                "textarea": {"maxLength": 1000}, "text": {"maxLength": 255},
                "password": {"minLength": 8}
            }
            defaults = type_defaults.get(field["type"], {})
            for key, default_val in defaults.items():
                val.setdefault(key, default_val)
            
            # Apply defaults from the field's definition in fields.json
            base_id = field.get('id', '').split('_')[0]
            base_field_def = self.field_map.get(base_id)
            if base_field_def:
                for key, base_val in base_field_def.validation.items():
                    val.setdefault(key, base_val)

            # Apply the final "required: false" default if no other required rule has been set
            val.setdefault('required', False)

        # Remove any fields that were meant to be excluded
        final_fields = [f for f in final_fields if f['id'] not in excluded_ids]

        # Step B: NOW, appling  the user's specific commands, which will OVERWRITE the defaults.
        def find_target_id_for_attribute(attr_pos, doc):
            search_window_start = max(0, attr_pos - 5)
            window = doc[search_window_start:attr_pos]
            for token in reversed(window):
                if token.pos_ in ['NOUN', 'PROPN']:
                    target_match = process.extractOne(token.lemma_, self.fuzzy_map.keys(), score_cutoff=85)
                    if target_match:
                        return self.fuzzy_map[target_match[0]]
            return None

        # appply required/optional attributes
        for attr in attributes:
            target_id = find_target_id_for_attribute(attr['pos'], doc)
            if not target_id:
                continue
            
            fields_to_modify = [f for f in final_fields if f['id'].startswith(target_id)]
            for field in fields_to_modify:
                if attr['rule'] == 'ATTR_REQUIRED':
                    field['validation']['required'] = True
                elif attr['rule'] == 'ATTR_OPTIONAL':
                    field['validation']['required'] = False
        
        # Apply dynamic numeric ranges
        for drange in dynamic_ranges:
            applicable_fields = [f for f in final_fields if f.get('type') in ['number', 'range'] and 'pos' in f]
            if applicable_fields:
                target_field = min(applicable_fields, key=lambda f: abs(f['pos'] - drange['pos']))
                # OVERWRITE existing validation with the new range info
                target_field['validation'].update({'min': drange['min'], 'max': drange['max']})
                target_field['type'] = 'range'
                target_field['label'] = f"{target_field.get('label', 'Rating').split(' (')[0]} ({drange['min']}-{drange['max']})"

        # Step C: Final structural cleanup
        final_fields = self.post_process_name_fields(final_fields)
        
        # Remove the temporary 'pos' key from all fields before returning
        for field in final_fields:
            field.pop('pos', None)

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