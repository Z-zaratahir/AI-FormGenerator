# expand_seeds_with_synonyms.py
# Script to expand seeds in schemas.json with at least 2 synonyms per seed using WordNet

import json
import os
from nltk.corpus import wordnet as wn
from nltk import download

# Ensure WordNet resources are downloaded
download('wordnet')
download('omw-1.4')

SCHEMA_FILE = "schemas.json"


def get_top_synonyms(word: str, count: int = 2) -> list:
    """Return top N synonyms for a word using WordNet."""
    synonyms = set()
    for syn in wn.synsets(word):
        for lemma in syn.lemmas():
            name = lemma.name().replace("_", " ").lower()
            if name != word.lower():
                synonyms.add(name)
            if len(synonyms) >= count:
                break
        if len(synonyms) >= count:
            break
    return list(synonyms)


def expand_schema_seeds():
    if not os.path.exists(SCHEMA_FILE):
        print(f"Error: {SCHEMA_FILE} not found.")
        return

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for schema_name, schema in data.items():
        original_seeds = schema.get("seed", [])
        expanded_seeds = set(word.lower() for word in original_seeds)

        for seed in original_seeds:
            synonyms = get_top_synonyms(seed, count=2)
            expanded_seeds.update(synonyms)

        schema["seed"] = list(expanded_seeds)
        print(f"Expanded '{schema_name}' seeds: {len(original_seeds)} → {len(expanded_seeds)}")

    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nUpdated '{SCHEMA_FILE}' with synonyms.")


if __name__ == "__main__":
    expand_schema_seeds()
