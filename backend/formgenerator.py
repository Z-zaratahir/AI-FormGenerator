# form_generator.py
# Main script for dynamic intent classification using external schemas and fuzzy matching only

from typing import List, Dict, Any
import json
from fuzzywuzzy import fuzz, process

# Load schemas (fields + seed keywords) from external JSON
with open("schemas.json", "r", encoding="utf-8") as f:
    SCHEMA_DATA: Dict[str, Dict[str, Any]] = json.load(f)

# Extract structures: fields and raw seeds
SCHEMAS: Dict[str, List[str]] = {
    name: data["fields"]
    for name, data in SCHEMA_DATA.items()
}
SCHEMA_SEEDS: Dict[str, List[str]] = {
    name: [s.lower() for s in data.get("seed", [])]
    for name, data in SCHEMA_DATA.items()
}

# Field-to-input-type mapping
FIELD_TYPES: Dict[str, str] = {
    "first_name": "text",
    "last_name": "text",
    "email": "email",
    "phone": "tel",
    "roll_no": "number",
    "date": "date",
    "time": "time",
    "rating": "number",
    "resume": "file",
    "cover_letter": "textarea",
    "address": "text"
}

# Matching thresholds
default_schema_threshold = 80
FIELD_THRESHOLD = 75

def fuzzy_match_schemas(prompt: str, threshold: int = default_schema_threshold) -> List[str]:
    """
    Return schemas whose seed keywords match the prompt, ranked by number of matching seeds and then by total score.
    """
    prompt_lc = prompt.lower()
    schema_stats = []  # list of (schema, match_count, total_score)
    for schema, seeds in SCHEMA_SEEDS.items():
        if not seeds:
            continue
        match_count = 0
        total_score = 0
        for seed in seeds:
            _, score = process.extractOne(prompt_lc, [seed], scorer=fuzz.partial_ratio)
            if score >= threshold:
                match_count += 1
                total_score += score
        if match_count > 0:
            schema_stats.append((schema, match_count, total_score))
    # sort by match_count desc, then total_score desc
    schema_stats.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [schema for schema, _, _ in schema_stats]

def build_form_spec(prompt: str) -> Dict[str, Any]:
    """
    Use fuzzy matching to classify the intent and generate a form specification.
    Fallback to field-level fuzzy matching if schema detection fails.
    """
    spec = {"type": "custom", "fields": []}

    schemas = fuzzy_match_schemas(prompt)

    if schemas:
        primary = schemas[0]
        spec["type"] = primary
        seen = set()
        for fld in SCHEMAS.get(primary, []):
            if fld not in seen:
                seen.add(fld)
                fld_type = FIELD_TYPES.get(fld, "text")
                spec["fields"].append({
                    "name": fld,
                    "type": fld_type,
                    "label": fld.replace("_", " ").title()
                })
        return spec

    # Fallback: fuzzy-match individual fields if no schema match
    all_fields = list({fld for fields in SCHEMAS.values() for fld in fields})
    seen = set()
    prompt_lc = prompt.lower()
    for fld in all_fields:
        _, score = process.extractOne(prompt_lc, [fld], scorer=fuzz.partial_ratio)
        if score >= FIELD_THRESHOLD and fld not in seen:
            seen.add(fld)
            fld_type = FIELD_TYPES.get(fld, "text")
            spec["fields"].append({
                "name": fld,
                "type": fld_type,
                "label": fld.replace("_", " ").title()
            })
    return spec

if __name__ == "__main__":
    # Example usage
    test_prompts = [

        "Give review for the python course",
        "Submit feedback for class",
        "Course rating and comments",
        "Rate your learning experience",
        "End-of-semester course feedback",

    ]
    for p in test_prompts:
        print(f"Prompt: {p}\nForm Spec: {build_form_spec(p)}\n")

# -----------------------------------------
# Install dependencies via pip:
# pip install fuzzywuzzy python-Levenshtein
# -----------------------------------------
