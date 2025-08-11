# CreatingDataset.py
import json
import spacy

print("Starting dataset creation...")

# Load your existing knowledge base
try:
    with open('fields.json', 'r', encoding='utf-8') as f:
        fields_data = json.load(f)
    with open('templates.json', 'r', encoding='utf-8') as f:
        templates_data = json.load(f)
except FileNotFoundError:
    print("FATAL: Make sure fields.json and templates.json are in the same directory.")
    exit()

nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])

def create_training_example(text, entities):
    doc = nlp(text)
    tags = ["O"] * len(doc)
    for start_char, end_char, label in entities:
        span = doc.char_span(start_char, end_char)
        if span is not None:
            tags[span.start] = f"B-{label}"
            for i in range(span.start + 1, span.end):
                tags[i] = f"I-{label}"
    return {"tokens": [tok.text for tok in doc], "tags": tags}

training_data = []

# 1. Generate data from your fields.json fuzzy_keywords
print("Generating examples from fields.json...")
for field in fields_data:
    for keyword in field.get('fuzzy_keywords', []):
        text = f"form with a {keyword} field"
        start = text.find(keyword)
        end = start + len(keyword)
        training_data.append(create_training_example(text, [(start, end, "FIELD_NAME")]))

# 2. Generate data from your templates.json seeds
print("Generating examples from templates.json...")
for template_id, data in templates_data.items():
    if isinstance(data, dict):
      for seed in data.get('seeds', []):
          text = f"make a {seed} form"
          start = text.find(seed)
          end = start + len(seed)
          training_data.append(create_training_example(text, [(start, end, "FORM_TYPE")]))

# 3. Add a few crucial manual examples for structure
print("Adding manual examples for quantifiers and attributes...")
manual_examples = [
    ("create 3 required reference boxes", [(7, 8, "QUANTITY"), (9, 17, "ATTRIBUTE"), (18, 33, "FIELD_NAME")]),
    ("a form with two optional comment fields", [(13, 16, "QUANTITY"), (17, 25, "ATTRIBUTE"), (26, 40, "FIELD_NAME")])
]
for text, entities_char in manual_examples:
    training_data.append(create_training_example(text, entities_char))

# Save the dataset
with open('TrainingData.json', 'w', encoding='utf-8') as f:
    json.dump(training_data, f, indent=2)

print(f"Success! Created 'TrainingData.json' with {len(training_data)} examples.")