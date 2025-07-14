# formgenerator.py
from typing import List, Dict, Any
import json
import re
from fuzzywuzzy import fuzz

# Load schemas
with open("schemas.json", "r", encoding="utf-8") as f:
    SCHEMA_DATA: Dict[str, Dict[str, Any]] = json.load(f)

# Prepare lists of fields and schemas
FIELDS: List[str] = [field["name"] for schema in SCHEMA_DATA.values() for field in schema["fields"]]
SCHEMA_LIST: List[str] = list(SCHEMA_DATA.keys())

# Build keyword-based schema mapping from seeds in schemas.json
SCHEMA_KEYWORDS: Dict[str, List[str]] = {
    schema_name: [seed.lower() for seed in data.get("seed", [])]
    for schema_name, data in SCHEMA_DATA.items()
}

# Threshold for fuzzy field matching
FUZZY_FIELD_THRESHOLD = 65

# Metadata lookup for fields
FIELD_META: Dict[str, Dict[str, Any]] = {
    field["name"]: field
    for data in SCHEMA_DATA.values() for field in data["fields"]
}
FIELD_TYPES: Dict[str, str] = {name: meta.get("type", "text") for name, meta in FIELD_META.items()}


def detect_schema(prompt: str) -> str:
    prompt_lower = prompt.lower()
    for schema_name in SCHEMA_LIST:
        if schema_name.replace('_', ' ') in prompt_lower:
            return schema_name
    for schema_name, seeds in SCHEMA_KEYWORDS.items():
        if any(seed in prompt_lower for seed in seeds):
            return schema_name
    return ""


def build_form_spec(prompt: str) -> Dict[str, Any]:
    prompt_lower = prompt.lower()
    override_fields: List[Dict[str, Any]] = []

    matched_flags = set()

    # Field-specific overrides with priority check
    if re.search(r"\b(resume|cv)\b", prompt_lower):
        matched_flags.add("resume")
        override_fields.append({
            "name": "resume",
            "type": FIELD_META.get("resume", {}).get("type", "file"),
            "family": FIELD_META.get("resume", {}).get("family", "file"),
            "validation": FIELD_META.get("resume", {}).get("validation", "file_type"),
            "accept": FIELD_META.get("resume", {}).get("accept", ".pdf,.doc,.docx"),
            "confidence": 1.0,
            "label": FIELD_META.get("resume", {}).get("label", "Upload Resume")
        })

    if "email" in prompt_lower and "email" not in matched_flags:
        matched_flags.add("email")
        override_fields.append({
            "name": "email",
            "type": FIELD_META.get("email", {}).get("type", "email"),
            "family": FIELD_META.get("email", {}).get("family", "email"),
            "validation": FIELD_META.get("email", {}).get("validation", "email_format"),
            "confidence": 1.0,
            "label": FIELD_META.get("email", {}).get("label", "Email")
        })

    if any(k in prompt_lower for k in ["phone", "mobile"]) and "phone" not in matched_flags:
        matched_flags.add("phone")
        override_fields.append({
            "name": "phone",
            "type": FIELD_META.get("phone", {}).get("type", "tel"),
            "family": FIELD_META.get("phone", {}).get("family", "textual"),
            "validation": FIELD_META.get("phone", {}).get("validation", "phone_number"),
            "confidence": 1.0,
            "label": FIELD_META.get("phone", {}).get("label", "Phone")
        })

    if any(k in prompt_lower for k in ["image", "photo", "picture"]):
        matched_flags.add("image")
        override_fields.append({
            "type": "file", "family": "file",
            "validation": "file_type", "accept": ".png,.jpg,.jpeg",
            "confidence": 1.0, "label": "Upload Image"
        })

    if (
    any(k in prompt_lower for k in ["file", "document", "upload"])
    and "resume" not in matched_flags
    and "image" not in matched_flags
    ):
        override_fields.append({
        "type": "file",
        "family": "file",
        "validation": "file_type",
        "accept": ".pdf,.doc,.docx,.txt",
        "confidence": 1.0,
        "label": "Upload File"
    })


    range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", prompt)
    if range_match and "rating" in prompt_lower:
        low, high = map(int, range_match.groups())
        override_fields.append({
            "type": "range", "family": "rating",
            "min": low, "max": high,
            "confidence": 1.0,
            "label": prompt.strip().capitalize()
        })
    elif any(k in prompt_lower for k in ["rating", "rate"]):
        override_fields.append({
            "name": "rating",
            "type": FIELD_META.get("rating", {}).get("type", "number"),
            "family": FIELD_META.get("rating", {}).get("family", "numeric"),
            "validation": FIELD_META.get("rating", {}).get("validation", "none"),
            "confidence": 1.0,
            "label": FIELD_META.get("rating", {}).get("label", "Rating")
        })

    if override_fields:
        return {"type": "custom", "fields": override_fields}

    detected = detect_schema(prompt)
    if detected:
        spec = {"type": detected, "fields": []}
        for field in SCHEMA_DATA[detected]["fields"]:
            name = field["name"]
            meta = FIELD_META.get(name, {})
            enriched = {
                "name": name,
                "type": meta.get("type", field.get("type", "text")),
                "family": meta.get("family", field.get("type", "text")),
                "validation": meta.get("validation", "none"),
                "label": meta.get("label", field.get("label", name.replace("_", " ").title()))
            }
            if "accept" in meta:
                enriched["accept"] = meta["accept"]
            spec["fields"].append(enriched)
        return spec

    spec = {"type": "custom", "fields": []}
    seen = set()
    prompt_words = prompt_lower.split()
    for fld in FIELDS:
        fld_lower = fld.lower()
        if any(word in fld_lower for word in prompt_words) and fld not in seen:
            seen.add(fld)
            meta = FIELD_META.get(fld, {})
            spec["fields"].append({
                "name": fld,
                "type": meta.get("type", FIELD_TYPES.get(fld, "text")),
                "label": meta.get("label", fld.replace("_", " ").title())
            })
            continue
        score = fuzz.partial_ratio(prompt_lower, fld_lower)
        if score >= FUZZY_FIELD_THRESHOLD and fld not in seen:
            seen.add(fld)
            meta = FIELD_META.get(fld, {})
            spec["fields"].append({
                "name": fld,
                "type": meta.get("type", FIELD_TYPES.get(fld, "text")),
                "label": meta.get("label", fld.replace("_", " ").title())
            })
    return spec


if __name__ == "__main__":
    prompts = [
        ### TEST PROMPTS
        "Customer email address",
        "Enter your phone number",
        "Upload your resume or CV",
        "Submit your profile picture",
        "Student ID and other details",
        "Provide feedback or suggestions",
        "What's your official email?",
        "Drop your phone number here",
        "Send over your CV please",
        "Upload an image of your product",
        "Rate our app between 1 to 5",
        "Give a rating from 1 to 10",
        "Fill out the student registration form",
        "Sign up for the webinar",
        "Take our customer feedback survey",
        "Enter your name and email",
        "Upload any supporting documents",
        "Choose your gender",
        "Add a short note or suggestion"
    ]
    for p in prompts:
        spec = build_form_spec(p)
        print(f"Prompt: {p}\nSpec: {json.dumps(spec, indent=2)}\n")


        
