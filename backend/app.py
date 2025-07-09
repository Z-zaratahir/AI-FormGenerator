from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span
from spacy.util import filter_spans
from rapidfuzz import process

app = Flask(__name__)
CORS(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])

print("Loading spaCy model...")
nlp = spacy.load("en_core_web_sm")
print("Model loaded.")

# --- 1. The Definitive Knowledge Base ---
class FieldDefinition:
    def __init__(self, id, label, type, patterns, fuzzy_keywords=None):
        self.id = id; self.label = label; self.type = type;
        self.patterns = patterns; self.fuzzy_keywords = fuzzy_keywords or []

FIELD_DEFINITIONS = [
    FieldDefinition("FIRST_NAME", "First Name", "text", [[{"LOWER": "first"}, {"LOWER": "name"}]], ["firstname"]),
    FieldDefinition("LAST_NAME", "Last Name", "text", [[{"LOWER": "last"}, {"LOWER": "name"}]], ["lastname", "surname"]),
    FieldDefinition("FULL_NAME", "Name", "text", [[{"LOWER": "name"}]], ["name"]),
    FieldDefinition("EMAIL", "Email", "email", [[{"LEMMA": "email"}]], ["email", "emial"]),
    FieldDefinition("PHONE", "Phone Number", "tel", [[{"LEMMA": "phone"}]], ["phone"]),
    FieldDefinition("PASSWORD", "Password", "password", [[{"LOWER": "password"}]], ["password"]),
    FieldDefinition("COUNTRY", "Country", "select", [[{"LEMMA": "country"}]], ["country"]),
    FieldDefinition("STATE", "State", "select", [[{"LEMMA": "state"}]], ["state"]),
    FieldDefinition("AGE", "Age", "number", [[{"LEMMA": "age"}]], ["age"]),
    FieldDefinition("RATING", "Rating", "number", [[{"LEMMA": "rate"}]], ["rating"]),
    FieldDefinition("SCORE", "Score", "number", [[{"LEMMA": "score"}]], ["score"]),
    FieldDefinition("COMMENTS", "Comments", "textarea", [[{"LEMMA": "comment"}]], ["comment"]),
    FieldDefinition("CHECKBOX", "Checkbox", "checkbox", [[{"LEMMA": "checkbox"}]], ["checkbox"]),
    FieldDefinition("SHORT_ANSWER", "Short Answer", "text", [[{"LOWER": "short"}, {"LEMMA": "answer"}]], ["answer"]),
]

# --- 2. The Final Form Generator Engine ---
class FormGenerator:
    def __init__(self):
        self.field_map = {f.id: f for f in FIELD_DEFINITIONS}
        self.fuzzy_map = {kw: f.id for f in FIELD_DEFINITIONS for kw in f.fuzzy_keywords}
        self.matcher = self._build_matcher()

    def _build_matcher(self):
        matcher = Matcher(nlp.vocab)
        for field in FIELD_DEFINITIONS: matcher.add(field.id, field.patterns)
        
        matcher.add("ATTR_DROPDOWN", [[{"LEMMA": "dropdown"}]])
        matcher.add("ATTR_REQUIRED", [[{"LOWER": "required"}]])
        matcher.add("ATTR_RANGE", [[{"LOWER": {"IN": ["from", "between"]}}, {"like_num": True}, {"LOWER": {"IN": ["to", "and"]}}, {"like_num": True}]])
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not"]}}]])
        matcher.add("LOGIC_QUANTIFIER", [[{"like_num": True}, {"POS": "NOUN", "OP": "+"} ]])
        return matcher

    def word_to_num(self, word):
        num_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        return num_map.get(word.lower(), None)

    def find_target_noun(self, doc, start, end):
        """Find the noun being referred to by an attribute or logic keyword."""
        for i in range(end, min(end + 3, len(doc))):
            if doc[i].pos_ == "NOUN": return doc[i]
        return None

    def find_closest_field(self, fields_with_pos, attr_start_pos):
        if not fields_with_pos: return None
        return min(fields_with_pos, key=lambda f: abs(f['pos'] - attr_start_pos))['field']

    def process_prompt(self, prompt):
        doc = nlp(prompt)
        all_matches = self.matcher(doc)
        
        # --- Multi-Pass Processing Pipeline ---

        # Pass 1: Handle high-level logic (Negations and Quantifiers)
        excluded_ids = set()
        quantities = {}
        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]
            target_noun = self.find_target_noun(doc, start, end)
            if not target_noun: continue

            target_match = process.extractOne(target_noun.lemma_, self.fuzzy_map.keys())
            if not target_match or target_match[1] < 85: continue
            target_field_id = self.fuzzy_map[target_match[0]]

            if rule_id == "LOGIC_NEGATION":
                excluded_ids.add(target_field_id)
            elif rule_id == "LOGIC_QUANTIFIER":
                num = self.word_to_num(doc[start].text) or int(doc[start].text)
                quantities[target_field_id] = num

        # Pass 2: Extract base entities, resolving overlaps
        spans = [Span(doc, s, e, label=nlp.vocab.strings[mid]) for mid, s, e in all_matches if nlp.vocab.strings[mid] in self.field_map]
        filtered_spans = filter_spans(spans)
        
        # Pass 3: Create fields based on entities, quantifiers, and negations
        fields, fields_with_pos, added_ids = [], [], set()
        
        # First, add quantified fields
        for field_id, num in quantities.items():
            if field_id in excluded_ids: continue
            field_def = self.field_map[field_id]
            for i in range(num):
                field_obj = {"label": f"{field_def.label} #{i+1}", "type": field_def.type, "source": "quantifier", "confidence": 0.95}
                fields.append(field_obj)
            added_ids.add(field_id)

        # Then, add remaining non-quantified fields
        for span in filtered_spans:
            field_id = span.label_
            if field_id not in added_ids and field_id not in excluded_ids:
                field_def = self.field_map[field_id]
                field_obj = {"label": field_def.label, "type": field_def.type, "source": "matcher", "confidence": 1.0}
                fields.append(field_obj)
                fields_with_pos.append({'field': field_obj, 'pos': span.start})
                added_ids.add(field_id)

        # Pass 4: Apply attributes to the closest created fields
        for match_id, start, end in all_matches:
            rule_id = nlp.vocab.strings[match_id]
            if not rule_id.startswith("ATTR_"): continue
            
            target_field = self.find_closest_field(fields_with_pos, start)
            if not target_field: continue
            
            if rule_id == "ATTR_DROPDOWN": target_field['type'] = 'select'
            elif rule_id == "ATTR_REQUIRED": target_field['required'] = True
            elif rule_id == "ATTR_RANGE" and target_field.get('type') == 'number':
                numbers = [int(t.text) for t in doc[start:end] if t.like_num]
                if len(numbers) == 2:
                    target_field['min'], target_field['max'] = min(numbers), max(numbers)

        # Pass 5: Handle special cases like 'password confirmation'
        password_field_index = -1
        for i, field in enumerate(fields):
            if field['label'] == 'Password':
                password_field_index = i
                break
        
        if password_field_index != -1 and "confirmation" in prompt.lower():
            confirm_field = {"label": "Confirm Password", "type": "password", "source": "logic", "confidence": 0.98}
            fields.insert(password_field_index + 1, confirm_field)
            
        return fields

form_gen = FormGenerator()

@app.route("/process", methods=["POST"])
def process_prompt_route():
    data = request.get_json()
    prompt = data.get("prompt", "")
    if not prompt: return jsonify({"error": "Prompt is empty"}), 400
    
    generated_fields = form_gen.process_prompt(prompt)
    return jsonify({"title": "Generated Form", "prompt": prompt, "fields": generated_fields})

if __name__ == "__main__":
    app.run(debug=True)