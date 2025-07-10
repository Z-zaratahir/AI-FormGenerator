from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import spacy
from spacy.matcher import Matcher
from spacy.tokens import Span
from spacy.util import filter_spans
from rapidfuzz import process
import re

app = Flask(__name__)
CORS(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])

print("Loading spaCy model...")
nlp = spacy.load("en_core_web_sm")
print("Model loaded.")

# --- 1. The Definitive, Massively Expanded Knowledge Base ---
class FieldDefinition:
    def __init__(self, id, label, type, patterns, fuzzy_keywords=None):
        self.id = id; self.label = label; self.type = type;
        self.patterns = patterns; self.fuzzy_keywords = fuzzy_keywords or []

FIELD_DEFINITIONS = [
    # --- Standard Personal Info ---
    FieldDefinition("FIRST_NAME", "First Name", "text", [[{"LOWER": "first"}, {"LOWER": "name"}], [{"LOWER": "given"}, {"LOWER": "name"}]], ["firstname"]),
    FieldDefinition("LAST_NAME", "Last Name", "text", [[{"LOWER": "last"}, {"LOWER": "name"}], [{"LOWER": "family"}, {"LOWER": "name"}]], ["lastname", "surname"]),
    FieldDefinition("FULL_NAME", "Full Name", "text", [[{"LOWER": "full"}, {"LOWER": "name"}], [{"LOWER": "name"}]], ["name"]),
    FieldDefinition("EMAIL", "Email Address", "email", [[{"LEMMA": "email"}]], ["email", "emial"]),
    FieldDefinition("PHONE", "Phone Number", "tel", [[{"LEMMA": "phone"}]], ["phone", "mobile"]),
    FieldDefinition("ADDRESS", "Street Address", "text", [[{"LOWER": "address"}]], ["address", "street"]),
    FieldDefinition("CITY", "City", "text", [[{"LOWER": "city"}]], ["city"]),
    FieldDefinition("STATE", "State / Province", "text", [[{"LOWER": "state"}]], ["state", "province"]),
    FieldDefinition("ZIP_CODE", "ZIP / Postal Code", "text", [[{"LOWER": {"IN": ["zip", "postal"]}}, {"LOWER": "code"}]], ["zip", "postalcode"]),
    FieldDefinition("COUNTRY", "Country", "select", [[{"LEMMA": "country"}]], ["country"]),
    FieldDefinition("DATE_OF_BIRTH", "Date of Birth", "date", [[{"LOWER": "date"}, {"LOWER": "of"}, {"LOWER": "birth"}], [{"LOWER": "dob"}]], ["dob", "birthday"]),
    
    # --- Account & Auth ---
    FieldDefinition("USERNAME", "Username", "text", [[{"LOWER": "username"}], [{"LOWER": "user"}, {"LOWER": "name"}]], ["username", "user", "userid"]),
    FieldDefinition("PASSWORD", "Password", "password", [[{"LOWER": "password"}]], ["password"]),
    FieldDefinition("CONFIRM_PASSWORD", "Confirm Password", "password", [[{"LOWER": "confirm"}, {"LOWER": "password"}]], ["confirm password"]),

    # --- Business & Work ---
    FieldDefinition("COMPANY_NAME", "Company Name", "text", [[{"LOWER": "company"}]], ["company", "organization"]),
    FieldDefinition("JOB_TITLE", "Job Title", "text", [[{"LOWER": "job"}, {"LOWER": "title"}]], ["job title", "role", "position"]),
    FieldDefinition("WEBSITE_URL", "Website URL", "url", [[{"LOWER": "website"}], [{"LOWER": "url"}]], ["website", "url", "site"]),
    FieldDefinition("PORTFOLIO_LINK", "Portfolio Link", "url", [[{"LOWER": "portfolio"}]], ["portfolio", "work"]),
    FieldDefinition("RESUME_UPLOAD", "Resume/CV", "file", [[{"LOWER": {"IN": ["resume", "cv"]}}]], ["resume", "cv"]),
    FieldDefinition("COVER_LETTER", "Cover Letter", "textarea", [[{"LOWER": "cover"}, {"LOWER": "letter"}]], ["cover letter"]),
    FieldDefinition("START_DATE", "Available Start Date", "date", [[{"LOWER": "start"}, {"LOWER": "date"}]], ["start date"]),
    FieldDefinition("SALARY_EXPECTATION", "Salary Expectation", "text", [[{"LOWER": "salary"}]], ["salary", "compensation"]),
    FieldDefinition("REFERENCES", "References", "textarea", [[{"LOWER": "references"}]], ["references"]),
    
    # --- E-Commerce & Orders ---
    FieldDefinition("ORDER_ID", "Order ID", "text", [[{"LOWER": "order"}, {"LOWER": "id"}]], ["order id", "order number"]),
    FieldDefinition("PRODUCT_NAME", "Product Name", "text", [[{"LOWER": "product"}, {"LOWER": "name"}]], ["product"]),
    FieldDefinition("QUANTITY", "Quantity", "number", [[{"LOWER": "quantity"}]], ["quantity", "qty"]),
    FieldDefinition("SHIPPING_ADDRESS", "Shipping Address", "textarea", [[{"LOWER": "shipping"}, {"LOWER": "address"}]], ["shipping address"]),
    FieldDefinition("BILLING_ADDRESS", "Billing Address", "textarea", [[{"LOWER": "billing"}, {"LOWER": "address"}]], ["billing address"]),
    
    # --- Events & Bookings ---
    FieldDefinition("EVENT_DATE", "Event Date", "date", [[{"LOWER": "event"}, {"LOWER": "date"}]], ["event date"]),
    FieldDefinition("NUM_ATTENDEES", "Number of Attendees", "number", [[{"LOWER": "attendees"}], [{"LOWER": "guests"}]], ["attendees", "guests"]),
    FieldDefinition("ATTENDING_CHOICE", "Will you be attending?", "radio", [[{"LOWER": "attending"}]], ["attending"]),
    FieldDefinition("DIETARY_RESTRICTIONS", "Dietary Restrictions", "textarea", [[{"LOWER": "dietary"}]], ["diet", "allergies"]),
    FieldDefinition("APPOINTMENT_DATE", "Appointment Date", "date", [[{"LOWER": "appointment"}, {"LOWER": "date"}]], ["appointment date"]),
    FieldDefinition("APPOINTMENT_TIME", "Appointment Time", "time", [[{"LOWER": "appointment"}, {"LOWER": "time"}]], ["appointment time"]),

    # --- Feedback & Surveys ---
    FieldDefinition("RATING", "Rating (1-5)", "number", [[{"LEMMA": "rate"}]], ["rating"]),
    FieldDefinition("SATISFACTION", "Satisfaction Level", "radio", [[{"LOWER": "satisfaction"}]], ["satisfaction"]),
    FieldDefinition("RECOMMEND_SCORE", "How likely are you to recommend us?", "number", [[{"LOWER": "recommend"}]], ["nps"]),
    FieldDefinition("COMMENTS", "Comments", "textarea", [[{"LEMMA": "comment"}]], ["comment"]),
    FieldDefinition("SUGGESTIONS", "Suggestions", "textarea", [[{"LOWER": "suggestions"}]], ["suggestions"]),

    # --- General & Miscellaneous ---
    FieldDefinition("SUBJECT", "Subject", "text", [[{"LOWER": "subject"}]], ["subject", "topic"]),
    FieldDefinition("MESSAGE", "Message", "textarea", [[{"LOWER": "message"}]], ["message", "body"]),
    FieldDefinition("TERMS_AND_CONDITIONS", "I agree to the Terms and Conditions", "checkbox", [[{"LOWER": "terms"}]], ["terms"]),
    FieldDefinition("EMERGENCY_CONTACT", "Emergency Contact", "text", [[{"LOWER": "emergency"}, {"LOWER": "contact"}]], ["emergency contact"]),
    FieldDefinition("HEAR_ABOUT_US", "How did you hear about us?", "select", [[{"LOWER": "hear"}, {"LOWER": "about"}]], ["source", "referral"]),
    
    # *** NEW GENERIC FIELD DEFINITIONS ***
    FieldDefinition("GENERIC_RADIO", "Choice", "radio", [[{"LOWER": "radio"}]], ["radio"]),
    FieldDefinition("GENERIC_CHECKBOX", "Option", "checkbox", [[{"LOWER": "checkbox"}]], ["checkbox"]),
    FieldDefinition("GENERIC_FILE_UPLOAD", "File Upload", "file", [[{"LOWER": "file"}, {"LOWER": "upload"}], [{"LOWER": "attachment"}]], ["upload", "attachment"]),
]

# --- The Comprehensive Form Template Library (Corrected) ---
FORM_TEMPLATES = {
    # --- Business & HR ---
    "contact": ["FULL_NAME", "EMAIL", "SUBJECT", "MESSAGE"],
    "lead_generation": ["FULL_NAME", "EMAIL", "PHONE", "COMPANY_NAME", "MESSAGE"],
    "support_ticket": ["FULL_NAME", "EMAIL", "ORDER_ID", "SUBJECT", "MESSAGE", "GENERIC_FILE_UPLOAD"],
    "bug_report": ["EMAIL", "WEBSITE_URL", "SUBJECT", "MESSAGE", "GENERIC_FILE_UPLOAD"],
    "job_application": ["FULL_NAME", "EMAIL", "PHONE", "ADDRESS", "RESUME_UPLOAD", "COVER_LETTER", "PORTFOLIO_LINK", "START_DATE", "SALARY_EXPECTATION"],
    "internship_application": ["FULL_NAME", "EMAIL", "PHONE", "PORTFOLIO_LINK", "RESUME_UPLOAD", "COVER_LETTER", "START_DATE"],
    "internship": ["FULL_NAME", "EMAIL", "PHONE", "PORTFOLIO_LINK", "RESUME_UPLOAD", "COVER_LETTER", "START_DATE"],
    "employee_onboarding": ["FULL_NAME", "DATE_OF_BIRTH", "ADDRESS", "PHONE", "EMERGENCY_CONTACT"],
    "expense_report": ["FULL_NAME", "EVENT_DATE", "SUBJECT", "MESSAGE", "GENERIC_FILE_UPLOAD"],

    # --- E-Commerce ---
    "product_order": ["FULL_NAME", "EMAIL", "SHIPPING_ADDRESS", "BILLING_ADDRESS"],
    "return_request": ["FULL_NAME", "EMAIL", "ORDER_ID", "PRODUCT_NAME", "MESSAGE"],
    "product_review": ["FULL_NAME", "EMAIL", "RATING", "COMMENTS"],

    # --- Events & Bookings ---
    "event_registration": ["FULL_NAME", "EMAIL", "NUM_ATTENDEES", "DIETARY_RESTRICTIONS"],
    "conference_registration": ["FULL_NAME", "EMAIL", "COMPANY_NAME", "JOB_TITLE", "DIETARY_RESTRICTIONS"],
    "appointment_booking": ["FULL_NAME", "EMAIL", "PHONE", "APPOINTMENT_DATE", "APPOINTMENT_TIME", "COMMENTS"],
    "rsvp": ["FULL_NAME", "EMAIL", "ATTENDING_CHOICE", "NUM_ATTENDEES", "DIETARY_RESTRICTIONS"],
    "volunteer_signup": ["FULL_NAME", "EMAIL", "PHONE", "START_DATE", "COMMENTS"],

    # --- Education ---
    "course_registration": ["FULL_NAME", "EMAIL", "PHONE", "SUBJECT"],
    "school_application": ["FULL_NAME", "DATE_OF_BIRTH", "ADDRESS", "EMAIL", "PHONE", "EMERGENCY_CONTACT", "COVER_LETTER"],

    # --- Healthcare (NOTE: Real forms need HIPAA compliance) ---
    "patient_intake": ["FULL_NAME", "DATE_OF_BIRTH", "ADDRESS", "PHONE", "EMAIL", "EMERGENCY_CONTACT"],
    "appointment_request": ["FULL_NAME", "PHONE", "DATE_OF_BIRTH", "APPOINTMENT_DATE", "MESSAGE"],

    # --- Real Estate & Property ---
    "rental_application": ["FULL_NAME", "EMAIL", "PHONE", "ADDRESS", "SALARY_EXPECTATION", "REFERENCES"],
    "maintenance_request": ["FULL_NAME", "PHONE", "ADDRESS", "MESSAGE", "GENERIC_FILE_UPLOAD"],
    "property_inquiry": ["FULL_NAME", "EMAIL", "PHONE", "MESSAGE"],

    # --- General & Personal ---
    "registration": ["USERNAME", "EMAIL", "PASSWORD", "CONFIRM_PASSWORD"],
    "login": ["USERNAME", "PASSWORD"],
    "feedback": ["FULL_NAME", "EMAIL", "SATISFACTION", "COMMENTS", "SUGGESTIONS"],
    "survey": ["EMAIL", "RATING", "RECOMMEND_SCORE", "COMMENTS", "HEAR_ABOUT_US"],
    "quote_request": ["FULL_NAME", "EMAIL", "PHONE", "COMPANY_NAME", "MESSAGE"],

    # --- Aliases for common requests ---
    "application": "job_application",
    "invitation": "rsvp",
    "booking": "appointment_booking",
    "patient_registration": "patient_intake",
    "contact_us": "contact",
    "new_hire": "employee_onboarding",
}

# --- 2. The Final Form Generator  ---
class FormGenerator:
    def __init__(self):
        self.field_map = {f.id: f for f in FIELD_DEFINITIONS}
        self.fuzzy_map = {kw: f.id for f in FIELD_DEFINITIONS for kw in f.fuzzy_keywords}
        # Add field labels to the fuzzy map for better negation matching
        for field in FIELD_DEFINITIONS:
            self.fuzzy_map[field.label.lower()] = field.id
        self.matcher = self._build_matcher()
        self.form_templates = self._resolve_template_aliases(FORM_TEMPLATES)

    def _resolve_template_aliases(self, templates):
        resolved = {}
        for key, value in templates.items():
            while isinstance(value, str):
                value = templates.get(value, [])
            resolved[key] = value
        return resolved

    def _build_matcher(self):
        matcher = Matcher(nlp.vocab)
        for field in FIELD_DEFINITIONS:
            matcher.add(field.id, field.patterns)

        # Attribute Patterns
        matcher.add("ATTR_REQUIRED", [[{"LOWER": "required"}]])
        
        # Logic Patterns - CORRECTED: Negation now includes "no"
        matcher.add("LOGIC_NEGATION", [[{"LOWER": {"IN": ["except", "without", "not", "don't", "no"]}}]])
        # Quantifier now allows for adjectives, e.g., "three separate suggestion boxes"
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

    # Re-engineered negation parser to handle lists with commas and conjunctions
    def find_all_negated_nouns(self, doc, start_index):
        nouns = []
        for i in range(start_index, min(start_index + 8, len(doc))):
            token = doc[i]
            # Stop if we hit another verb, indicating the end of the clause
            if token.pos_ == "VERB" and nouns: break
            
            if token.pos_ == "NOUN":
                # Handle compound nouns like "job title"
                compound_noun_span = doc[i:i+2] if i + 1 < len(doc) and doc[i+1].pos_ in ['NOUN', 'PROPN'] else doc[i:i+1]
                if not any(compound_noun_span.text in n for n in nouns):
                     nouns.append(compound_noun_span.text)
        return nouns
    
    # NEW: Smart de-duplication for name fields
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

        # Step 1: More specific Template Detection
        template_field_ids = []
        # Sort keys to check for longer, more specific templates first
        sorted_keys = sorted([k for k in self.form_templates.keys() if not isinstance(self.form_templates[k], str)], key=len, reverse=True)
        for key in sorted_keys:
            pattern = r'\b' + re.escape(key).replace('_', r'\s?') + r'\b'
            if re.search(pattern, prompt.lower()):
                template_field_ids = self.form_templates.get(key, [])
                break # Found the most specific match
        
        # Step 2: Assemble fields from Quantifiers
        for field_id, data in quantities.items():
            if field_id in excluded_ids: continue
            field_def = self.field_map[field_id]
            for i in range(data['num']):
                candidate_fields.append({"id": field_id, "label": f"{field_def.label} #{i+1}", "type": field_def.type, "source": "quantifier", "confidence": 0.95, "pos": data['pos']})
            added_ids.add(field_id)

        # Step 3: Add explicit matches
        for field_id, pos in explicit_ids:
             if field_id not in added_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append({"id": field_id, "label": field_def.label, "type": field_def.type, "source": "matcher", "confidence": 1.0, "pos": pos})
                added_ids.add(field_id)

        # Step 4: Add fields from template if not already added
        for field_id in template_field_ids:
            if field_id not in added_ids:
                field_def = self.field_map[field_id]
                candidate_fields.append({"id": field_id, "label": field_def.label, "type": field_def.type, "source": "template", "confidence": 0.90})
                added_ids.add(field_id)
        
        # Step 5: Add arbitrary fields
        for field in arbitrary_fields:
            field['confidence'] = 0.85
            candidate_fields.append(field)

        # --- Phase 3: Filtering & Attribute Application ---
        
        # Apply Negations to the entire generated list
        final_fields = [f for f in candidate_fields if f.get('id') not in excluded_ids]

        # Apply Attributes to the final list of fields
        for attr in attributes:
            if not final_fields: continue
            fields_with_pos = [f for f in final_fields if 'pos' in f]
            if not fields_with_pos: continue
            
            target_field = min(fields_with_pos, key=lambda f: abs(f['pos'] - attr['pos']))
            
            if attr['rule'] == "ATTR_REQUIRED":
                # FIX: If the target field was created by a quantifier, apply to all in the group
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

form_gen = FormGenerator()

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