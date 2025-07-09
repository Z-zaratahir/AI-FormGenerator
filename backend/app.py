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
    # Refined Fuzzy Keywords to be more specific and avoid ambiguity
    FieldDefinition("FIRST_NAME", "First Name", "text", [[{"LOWER": "first"}, {"LOWER": "name"}]], ["firstname"]),
    FieldDefinition("LAST_NAME", "Last Name", "text", [[{"LOWER": "last"}, {"LOWER": "name"}]], ["lastname", "surname"]),
    FieldDefinition("FULL_NAME", "Name", "text", [[{"LOWER": "name"}]], ["name"]), # General fallback
    FieldDefinition("EMAIL", "Email", "email", [[{"LEMMA": "email"}]], ["email", "emial"]),
    FieldDefinition("PHONE", "Phone Number", "tel", [[{"LEMMA": "phone"}]], ["phone"]),
    FieldDefinition("COUNTRY", "Country", "select", [[{"LEMMA": "country"}]], ["country"]),
    FieldDefinition("RATING", "Rating", "number", [[{"LEMMA": "rate"}]], ["rating"]),
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
        return matcher

    def _extract_entities(self, doc):
        """A unified pass to find the BEST fields, resolving overlaps."""
        
        # 1. Get all raw matches from the matcher
        matcher_matches = self.matcher(doc)
        
        # 2. Convert matches to Span objects and filter them

        spans = []
        for match_id, start, end in matcher_matches:
            rule_id = nlp.vocab.strings[match_id]
            if rule_id in self.field_map:
                spans.append(Span(doc, start, end, label=rule_id))
        
        filtered_spans = filter_spans(spans)
        
        entities = [{'id': span.label_, 'start': span.start, 'end': span.end, 'source': 'matcher'} for span in filtered_spans]
        matched_indices = {i for span in filtered_spans for i in range(span.start, span.end)}
        
        # 3. Add Fuzzy hits for typos, only on un-matched tokens
        for i, token in enumerate(doc):
            if i in matched_indices or len(token.text) < 3: continue
            
            match = process.extractOne(token.lower_, self.fuzzy_map.keys(), score_cutoff=88)
            if match:
                keyword, score, _ = match
                entities.append({'id': self.fuzzy_map[keyword], 'start': i, 'end': i + 1, 'source': f"fuzzy (from '{token.text}')", 'confidence': round(score/100,2)})

        return sorted(entities, key=lambda x: x['start'])

    def find_closest_field(self, fields_with_pos, attr_start_pos):
        if not fields_with_pos: return None
        closest_field_info = min(fields_with_pos, key=lambda f: abs(f['pos'] - attr_start_pos))
        return closest_field_info['field']

    def process_prompt(self, prompt):
        doc = nlp(prompt)
        
        # Pass 1: Extract the best, non-overlapping fields
        found_entities = self._extract_entities(doc)
        
        # Pass 2: Create the initial list of fields
        fields, fields_with_pos, added_ids = [], [], set()
        for entity in found_entities:
            field_id = entity['id']
            if field_id not in added_ids:
                field_def = self.field_map[field_id]
                field_obj = {
                    "label": field_def.label, "type": field_def.type,
                    "source": entity.get('source', 'unknown'), "confidence": entity.get('confidence', 1.0)
                }
                fields.append(field_obj)
                fields_with_pos.append({'field': field_obj, 'pos': entity['start']})
                added_ids.add(field_id)

        # Pass 3: Find and apply attributes to the closest fields
        attribute_matches = self.matcher(doc)
        for match_id, start, end in attribute_matches:
            rule_id = nlp.vocab.strings[match_id]
            if not rule_id.startswith("ATTR_"): continue
            
            target_field = self.find_closest_field(fields_with_pos, start)
            if not target_field: continue
            
            if rule_id == "ATTR_DROPDOWN": target_field['type'] = 'select'
            elif rule_id == "ATTR_REQUIRED": target_field['required'] = True
            elif rule_id == "ATTR_RANGE" and target_field['type'] == 'number':
                numbers = [int(t.text) for t in doc[start:end] if t.like_num]
                if len(numbers) == 2:
                    target_field['min'] = min(numbers)
                    target_field['max'] = max(numbers)
        
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