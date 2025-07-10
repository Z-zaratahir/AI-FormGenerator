# form_generator_dynamic.py
# Dynamic schema & field matching with semantic similarity

from typing import List, Dict, Any
import json
from sentence_transformers import SentenceTransformer, util
from fuzzywuzzy import fuzz, process
import numpy as np

# Load schemas (fields + seed keywords + optional descriptions) from external JSON
with open("schemas.json", "r", encoding="utf-8") as f:
    SCHEMA_DATA: Dict[str, Dict[str, Any]] = json.load(f)

# Initialize semantic model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Precompute embeddings for seeds and schema descriptions
SCHEMA_EMBS: Dict[str, np.ndarray] = {}
for name, data in SCHEMA_DATA.items():
    # combine seeds and optional description
    text = " ".join(data.get("seed", []))
    desc = data.get("description", "")
    if desc:
        text += " " + desc
    SCHEMA_EMBS[name] = model.encode(text, convert_to_tensor=True)

# Field-level mapping and embeddings
FIELDS = list({fld for d in SCHEMA_DATA.values() for fld in d["fields"]})
FIELD_EMBS = model.encode(FIELDS, convert_to_tensor=True)
FIELD_TYPES: Dict[str, str] = SCHEMA_DATA.get("_field_types", {})  # optional in JSON

# Matching thresholds
SEMANTIC_SCHEMA_THRESHOLD = 0.4  # cosine similarity
SEMANTIC_FIELD_THRESHOLD = 0.35
FUZZY_FIELD_THRESHOLD = 75


def semantic_match_schemas(prompt: str, top_k: int = 3) -> List[str]:
    """
    Return top-k schemas by cosine similarity between prompt and seed+desc text.
    """
    prompt_emb = model.encode(prompt, convert_to_tensor=True)
    scores = {name: float(util.cos_sim(prompt_emb, emb)) for name, emb in SCHEMA_EMBS.items()}
    # filter by threshold
    matched = [(name, score) for name, score in scores.items() if score >= SEMANTIC_SCHEMA_THRESHOLD]
    # sort by score desc
    matched.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in matched[:top_k]]


def build_form_spec(prompt: str) -> Dict[str, Any]:
    spec = {"type": "custom", "fields": []}

    # 1) semantic schema matching
    schemas = semantic_match_schemas(prompt)

    if schemas:
        primary = schemas[0]
        spec["type"] = primary
        for fld in SCHEMA_DATA[primary]["fields"]:
            spec["fields"].append({
                "name": fld,
                "type": FIELD_TYPES.get(fld, "text"),
                "label": fld.replace("_", " ").title()
            })
        return spec

    # 2) semantic & fuzzy field-level matching
    prompt_emb = model.encode(prompt, convert_to_tensor=True)
    cos_sims = util.cos_sim(prompt_emb, FIELD_EMBS)[0].tolist()
    for idx, fld in enumerate(FIELDS):
        if cos_sims[idx] >= SEMANTIC_FIELD_THRESHOLD:
            spec["fields"].append({
                "name": fld,
                "type": FIELD_TYPES.get(fld, "text"),
                "label": fld.replace("_", " ").title()
            })
    # fallback fuzzy
    if not spec["fields"]:
        for fld in FIELDS:
            _, score = process.extractOne(prompt.lower(), [fld], scorer=fuzz.partial_ratio)
            if score >= FUZZY_FIELD_THRESHOLD:
                spec["fields"].append({
                    "name": fld,
                    "type": FIELD_TYPES.get(fld, "text"),
                    "label": fld.replace("_", " ").title()
                })
    return spec


if __name__ == "__main__":
    prompts = [
        "Register me for the enrollment process",
        "I want to pay entrance fee and sign up",
        "Give feedback on the course you attended",
        "Submit address and contact details",
    ]
    for p in prompts:
        spec = build_form_spec(p)
        print(f"Prompt: {p}\n Spec: {json.dumps(spec, indent=2)}\n")
