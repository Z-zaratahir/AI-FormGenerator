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
    """Loads field definitions and form templates from JSON files."""
    try:
        with open(fields_path, 'r', encoding='utf-8') as f:
            fields_data = json.load(f)
        with open(templates_path, 'r', encoding='utf-8') as f:
            templates_data = json.load(f)
        print("Knowledge base loaded successfully from JSON files.")
        return fields_data, templates_data
    except FileNotFoundError as e:
        print(f"Error: Could not find a required knowledge base file: {e}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Could not parse a JSON file. Check for syntax errors: {e}")
        exit(1)

# --- Helper Class for Field Data ---
class FieldDefinition:
    """A simple class to hold structured data for each field."""
    def __init__(self, id, label, type, patterns, fuzzy_keywords=None):
        self.id = id
        self.label = label
        self.type = type
        self.patterns = patterns
        self.fuzzy_keywords = fuzzy_keywords or []

# --- The Form Generator Engine ---
class FormGenerator:
    def __init__(self, fields_data, templates_data):
        # 1. Process loaded field data into FieldDefinition objects
        field_definitions = [FieldDefinition(**data) for data in fields_data]
        
        # 2. Build internal maps and matchers from the structured objects
        self.field_map = {f.id: f for f in field_definitions}
        self.fuzzy_map = {kw: f.id for f in field_definitions for kw in f.fuzzy_keywords}
        for field in field_definitions:
            self.fuzzy_map[field.label.lower()] = field.id
            
        self.matcher = self._build_matcher(field_definitions)
        self.form_templates = self._resolve_template_aliases(templates_data)

    def _resolve_template_aliases(self, templates):
        resolved = {}
        for key, value in templates.items():
            while isinstance(value, str):
                value = templates.get(value, [])
            resolved[key] = value
        return resolved

    def _build_matcher(self, field_definitions):
        matcher = Matcher(nlp.vocab)
        for field in field_definitions:
            matcher.add(field.id, field.patterns)

        # Attribute & Logic Patterns
        matcher.add("ATTR_REQUIRED", [[{"LOWER": "required"}]])
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not", "don't", "no"]}}]])
        matcher.add("LOGIC_QUANTIFIER", [[{"like_num": True}, {"OP": "*"}, {"POS": "NOUN"}]])
        matcher.add("LOGIC_ARBITRARY_FIELD", [
            [{"LOWER": {"IN": ["a", "an"]}}, {"LOWER": "field"}, {"LOWER": "for"}],
            [{"LOWER": {"IN": ["a", "an"]}}, {"LOWER": "input"}, {"LOWER": "for"}]
        ])
        return matcher

    def word_to_num(self, word):
        num_map = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }
        return num_map.get(word.lower(), None)

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
        excluded_ids, quantities, arbitrary_fields, attributes, explicit_ids = set(), {}, [], [], set()

        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]

            if rule_id.startswith("LOGIC_"):
                if rule_id == "LOGIC_NEGATION":
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
                            field_id = self.fuzzy_map[target_match[0]]
                            quantities[field_id] = {"num": num, "pos": start}
                elif rule_id == "LOGIC_ARBITRARY_FIELD":
                    label_text = doc[end:].text.split(',')[0].split(' and ')[0].strip().strip("'\"")
                    if label_text:
                        arbitrary_fields.append({"label": label_text.title(), "type": "text", "source": "arbitrary", "pos": start})
            
            elif rule_id.startswith("ATTR_"):
                attributes.append({"rule": rule_id, "pos": start})

            elif rule_id in self.field_map:
                explicit_ids.add( (rule_id, start) )
        
        # --- Phase 2: Field Generation ---
        candidate_fields = []
        added_ids = set()

        # Step 1: Template Detection
        template_field_ids = []
        sorted_keys = sorted([k for k in self.form_templates.keys() if not isinstance(self.form_templates[k], str)], key=len, reverse=True)
        for key in sorted_keys:
            pattern = r'\b' + re.escape(key).replace('_', r'\s?') + r'\b'
            if re.search(pattern, prompt.lower()):
                template_field_ids = self.form_templates.get(key, [])
                break
        
        # Step 2: Quantifiers
        for field_id, data in quantities.items():
            if field_id in excluded_ids: continue
            field_def = self.field_map[field_id]
            for i in range(data['num']):
                candidate_fields.append({"id": field_id, "label": f"{field_def.label} #{i+1}", "type": field_def.type, "source": "quantifier", "confidence": 0.95, "pos": data['pos']})
            added_ids.add(field_id)

        # Step 3: Explicit matches
        for field_id, pos in explicit_ids:
             if field_id not in added_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append({"id": field_id, "label": field_def.label, "type": field_def.type, "source": "matcher", "confidence": 1.0, "pos": pos})
                added_ids.add(field_id)

        # Step 4: Template fields
        for field_id in template_field_ids:
            if field_id not in added_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append({"id": field_id, "label": field_def.label, "type": field_def.type, "source": "template", "confidence": 0.90})
                added_ids.add(field_id)
        
        # Step 5: Arbitrary fields
        for field in arbitrary_fields:
            field['confidence'] = 0.85
            candidate_fields.append(field)

        # --- Phase 3: Filtering & Attribute Application ---
        final_fields = [f for f in candidate_fields if f.get('id') not in excluded_ids]

        for attr in attributes:
            if not final_fields: continue
            fields_with_pos = [f for f in final_fields if 'pos' in f]
            if not fields_with_pos: continue
            
            target_field = min(fields_with_pos, key=lambda f: abs(f['pos'] - attr['pos']))
            
            if attr['rule'] == "ATTR_REQUIRED":
                if target_field.get('source') == 'quantifier':
                    quantifier_id = target_field.get('id')
                    for field in final_fields:
                        if field.get('id') == quantifier_id and field.get('source') == 'quantifier':
                            field['required'] = True
                else:
                    target_field['required'] = True
        
        # --- Phase 4: Post-Processing and Cleanup ---
        final_fields = self.post_process_name_fields(final_fields)
        
        for field in final_fields: field.pop('pos', None)
        
        password_field_index = -1
        for i, field in enumerate(final_fields):
            if field.get('id') == 'PASSWORD':
                password_field_index = i
        if password_field_index != -1 and "CONFIRM_PASSWORD" not in added_ids:
             if re.search(r"\b(confirm|confirmation|retype).{0,5}password", prompt.lower()):
                final_fields.insert(password_field_index + 1, {"id": "CONFIRM_PASSWORD", "label": "Confirm Password", "type": "password", "source": "logic", "confidence": 0.98})

        return final_fields

# --- Main Application Setup ---
# Load data from external files
fields_data, templates_data = load_knowledge_base('fields.json', 'templates.json')

# Create a single, reusable instance of the generator
form_gen = FormGenerator(fields_data, templates_data)

@app.route("/process", methods=["POST"])
def process_prompt_route():
    data = request.get_json()
    prompt = data.get("prompt", "")
    if not prompt: return jsonify({"error": "Prompt is empty"}), 400
    
    generated_fields = form_gen.process_prompt(prompt)
    if not generated_fields:
        return jsonify({"title": "Could not generate form", "prompt": prompt, "fields": [], "message": "I couldn't understand the type of form you want. Try being more specific, like 'a contact form' or 'an internship application form'."})
        
    return jsonify({"title": "Generated Form", "prompt": prompt, "fields": generated_fields})

if __name__ == "__main__":
    app.run(debug=True)