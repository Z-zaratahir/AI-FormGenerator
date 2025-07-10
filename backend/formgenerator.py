# form_generator_dynamic.py
# Dynamic schema & field matching with semantic similarity, range/email overrides, and enriched schema outputs

from typing import List, Dict, Any
import json
import re
from sentence_transformers import SentenceTransformer, util
from fuzzywuzzy import fuzz, process
import numpy as np

# Load schemas (fields include metadata dictionaries) from external JSON
with open("schemas.json", "r", encoding="utf-8") as f:
    SCHEMA_DATA: Dict[str, Dict[str, Any]] = json.load(f)

# Initialize semantic model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Precompute embeddings for seeds and schema descriptions
SCHEMA_EMBS: Dict[str, np.ndarray] = {}
for name, data in SCHEMA_DATA.items():
    text = " ".join(data.get("seed", []))
    desc = data.get("description", "")
    if desc:
        text += " " + desc
    SCHEMA_EMBS[name] = model.encode(text, convert_to_tensor=True)

# Field-level mapping and embeddings
FIELDS: List[str] = [field["name"] for schema in SCHEMA_DATA.values() for field in schema["fields"]]
FIELD_EMBS = model.encode(FIELDS, convert_to_tensor=True)

# Build a metadata lookup for fields
FIELD_META: Dict[str, Dict[str, Any]] = {
    field["name"]: field for schema in SCHEMA_DATA.values() for field in schema["fields"]
}

# Map each field to its type (for fallback)
FIELD_TYPES: Dict[str, str] = {name: meta.get("type", "text") for name, meta in FIELD_META.items()}

# Matching thresholds
SEMANTIC_SCHEMA_THRESHOLD = 0.4   # cosine similarity for schemas
SEMANTIC_FIELD_THRESHOLD = 0.50   # cosine similarity for general fields
FUZZY_FIELD_THRESHOLD = 75
SINGLE_FIELD_THRESHOLD = 0.6     # lowered threshold for single-field override


def semantic_match_schemas(prompt: str, top_k: int = 3) -> List[str]:
    prompt_emb = model.encode(prompt, convert_to_tensor=True)
    scores = {name: float(util.cos_sim(prompt_emb, emb)) for name, emb in SCHEMA_EMBS.items()}
    matched = [(name, score) for name, score in scores.items() if score >= SEMANTIC_SCHEMA_THRESHOLD]
    matched.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in matched[:top_k]]


def build_form_spec(prompt: str) -> Dict[str, Any]:
    # Detect numeric range pattern (e.g., "1-10", "1 to 10")
    range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)", prompt)
    prompt_emb = model.encode(prompt, convert_to_tensor=True)

    # Compute field similarities
    cos_sims = util.cos_sim(prompt_emb, FIELD_EMBS)[0].tolist()
    best_idx = int(np.argmax(cos_sims))
    best_score = cos_sims[best_idx]
    best_field = FIELDS[best_idx]

    # 0) Range override for rating
    if range_match and best_field == "rating":
        low, high = map(int, range_match.groups())
        return {
            "type": "range",
            "family": "rating",
            "min": low,
            "max": high,
            "confidence": round(best_score, 2),
            "label": prompt.strip().capitalize()
        }

    # 1) Email override: explicit "email" in prompt
    if "email" in prompt.lower():
        # Always return email family as 'email'
        score = round(float(util.cos_sim(prompt_emb, model.encode("email", convert_to_tensor=True))), 2)
        return {
            "type": "email",
            "family": "email",
            "validation": FIELD_META.get("email", {}).get("validation", "email_format"),
            "confidence": score,
            "label": prompt.strip().title()
        }

    # 2) Single-field override: strong semantic match
    if best_score >= SINGLE_FIELD_THRESHOLD:
        meta = FIELD_META[best_field].copy()
        meta_conf = round(best_score, 2)
        return {
            "type": meta.get("type", "text"),
            "family": meta.get("family", meta.get("type", "text")),
            "validation": meta.get("validation", "none"),
            **({"accept": meta.get("accept")} if "accept" in meta else {}),
            "confidence": meta_conf,
            "label": meta.get("label", best_field.replace("_", " ").title())
        }

    # 3) Semantic schema matching (full form)
    schemas = semantic_match_schemas(prompt)
    if schemas:
        spec: Dict[str, Any] = {"type": schemas[0], "fields": []}
        for field_meta in SCHEMA_DATA[schemas[0]]["fields"]:
            name = field_meta["name"]
            meta = FIELD_META.get(name, {})
            enriched = {
                "name": name,
                "type": meta.get("type", field_meta.get("type", "text")),
                "family": meta.get("family", meta.get("type", field_meta.get("type", "text"))),
                "validation": meta.get("validation", "none"),
                "label": meta.get("label", field_meta.get("label", name.replace("_", " ").title()))
            }
            if "accept" in meta:
                enriched["accept"] = meta["accept"]
            spec["fields"].append(enriched)
        return spec

    # 4) Semantic & fuzzy fallback multi-field
    spec = {"type": "custom", "fields": []}
    seen = set()
    for idx, fld in enumerate(FIELDS):
        if cos_sims[idx] >= SEMANTIC_FIELD_THRESHOLD and fld not in seen:
            seen.add(fld)
            meta = FIELD_META.get(fld, {})
            spec["fields"].append({
                "name": fld,
                "type": meta.get("type", FIELD_TYPES.get(fld, "text")),
                "label": meta.get("label", fld.replace("_", " ").title())
            })
    if not spec["fields"]:
        for fld in FIELDS:
            _, score = process.extractOne(prompt.lower(), [fld], scorer=fuzz.partial_ratio)
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
        "customer email address",
        "satisfaction rating 1-10",
        "upload your resume",
        "write a feedback form for students to fill",
        "write a form so students can comment and rate between 1-10",
        "write a form for job vacancy"
    ]
    for p in prompts:
        spec = build_form_spec(p)
        print(f"Prompt: {p}\nSpec: {json.dumps(spec, indent=2)}\n")

