# form_generator.py

from typing import List, Optional, Dict, Any
from fuzzywuzzy import fuzz, process

# 1. Hard‑coded schema fields
SCHEMAS: Dict[str, List[str]] = {
    "student_form":        ["first_name", "last_name", "roll_no", "phone", "email", "address"],
    "survey":              ["short_answer", "mcq", "rating"],
    "feedback":            ["course_name", "rating", "comments"],
    "job_application":     ["full_name", "email", "phone", "resume", "cover_letter"],
    "event_registration":  ["participant_name", "event_name", "email", "date", "time"],
    "bug_report":          ["reporter_name", "issue_type", "description", "screenshot", "priority"],
}

# 2. Hard‑coded schema‑related keywords for intent detection
SCHEMA_KEYWORDS: Dict[str, List[str]] = {
    "student_form":       ["registration", "admission", "student"],
    "survey":             ["survey", "questionnaire", "poll", "research"],
    "feedback":           ["feedback", "review", "course feedback"],
    "job_application":    ["job", "application", "resume", "career", "cv", "job app"],
    "event_registration": ["event", "register", "signup", "conference", "webinar"],
    "bug_report":         ["bug", "error", "issue", "crash", "report", "problem"],
}

# 3. Field type overrides (field_name -> HTML input type or component)
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

# 4. Fuzzy matching thresholds
SCHEMA_THRESHOLD = 80
FIELD_THRESHOLD = 75


def fuzzy_match_schemas(prompt: str) -> List[str]:
    """
    Return all schemas whose keywords match the prompt above threshold.
    """
    matched = []
    for schema, keywords in SCHEMA_KEYWORDS.items():
        _, score = process.extractOne(prompt, keywords, scorer=fuzz.partial_ratio)
        if score >= SCHEMA_THRESHOLD:
            matched.append(schema)
    return matched


def build_form_spec(prompt: str) -> Dict[str, Any]:
    """
    1) Find all matching schemas and combine their fields.
    2) If none match, fuzzy‑match prompt to all known fields.
    """
    spec = {"type": "custom", "fields": []}
    schemas = fuzzy_match_schemas(prompt)

    # If any schemas matched, merge fields
    if schemas:
        spec["type"] = "+".join(schemas)
        seen = set()
        for schema in schemas:
            for fld in SCHEMAS[schema]:
                if fld not in seen:
                    seen.add(fld)
                    fld_type = FIELD_TYPES.get(fld, "text")
                    spec["fields"].append({
                        "name": fld,
                        "type": fld_type,
                        "label": fld.replace("_", " ").title()
                    })
        return spec

    # Fallback: no schema match → match individual fields
    all_fields = list({fld for fields in SCHEMAS.values() for fld in fields})
    seen = set()
    for fld in all_fields:
        _, score = process.extractOne(prompt, [fld], scorer=fuzz.partial_ratio)
        if score >= FIELD_THRESHOLD and fld not in seen:
            seen.add(fld)
            fld_type = FIELD_TYPES.get(fld, "text")
            spec["fields"].append({
                "name": fld,
                "type": fld_type,
                "label": fld.replace("_", " ").title()
            })
    return spec


# Example usage:
if __name__ == "__main__":
    prompts = [
        "I want to generate form for students on data science in todays world"
    ]
    for p in prompts:
        print(f"Prompt: {p}\nForm Spec: {build_form_spec(p)}\n")