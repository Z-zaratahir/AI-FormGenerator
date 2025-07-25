# validate_and_repair.py (Final Version without Semantic Warnings)
import json
import spacy
import re

# Use a lightweight spaCy model just for tokenization.
nlp = spacy.load("en_core_web_sm", disable=["parser", "tagger", "ner", "attribute_ruler", "lemmatizer"])

def repair_and_validate(file_path):
    print(f"--- Loading and Validating: {file_path} ---")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print("✅ JSON format is valid.")
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not read file. Error: {e}")
        return

    original_data_copy = [dict(item) for item in data]
    repaired_data = []
    error_count = 0
    repair_count = 0

    for i, example in enumerate(data):
        example_num = i + 1
        
        if "tokens" not in example or "tags" not in example:
            print(f"⚠️  WARNING in example #{example_num}: Skipping due to missing 'tokens' or 'tags' key.")
            continue
            
        original_tokens = example["tokens"]
        original_tags = example["tags"]
        
        # --- ROBUST REPAIR STRATEGY ---
        
        # Step 1: Intelligently reconstruct the original text.
        text = "".join([f" {tok}" if not re.match(r"^[',.?!)\]]", tok) else tok for tok in original_tokens]).lstrip()

        # Step 2: Re-tokenize with spaCy to get the ground truth tokens.
        doc = nlp(text)
        new_tokens = [token.text for token in doc]
        
        # Step 3: Align old tags to the new, correct tokens.
        new_tags = []
        original_token_index = 0
        current_reconstructed_word = ""

        for new_token in new_tokens:
            tag_to_assign = "O"
            if original_token_index < len(original_tokens):
                current_reconstructed_word += new_token
                
                if current_reconstructed_word == original_tokens[original_token_index]:
                    if original_token_index < len(original_tags):
                        tag_to_assign = original_tags[original_token_index]
                    original_token_index += 1
                    current_reconstructed_word = ""
                elif original_tokens[original_token_index].startswith(current_reconstructed_word):
                    if original_token_index < len(original_tags):
                        tag_to_assign = original_tags[original_token_index]

            new_tags.append(tag_to_assign)
            
        # Step 4: Fix BIO logical errors automatically
        for j, tag in enumerate(new_tags):
            if tag.startswith("I-"):
                if j == 0 or new_tags[j-1] == "O":
                    new_tags[j] = "B-" + tag[2:]
                elif new_tags[j-1].startswith(("B-", "I-")) and new_tags[j-1][2:] != tag[2:]:
                    new_tags[j] = "B-" + tag[2:]

        # Step 5: Final length check after all repairs
        if len(new_tokens) != len(new_tags):
            print(f"❌ UNRECOVERABLE ERROR in example #{example_num}: Could not align tags to tokens. Requires manual deletion or fixing.")
            error_count += 1
            repaired_data.append(original_data_copy[i])
        else:
            if new_tokens != original_tokens or new_tags != original_tags:
                repair_count += 1
                print(f"🔧 REPAIRED example #{example_num}.")
            repaired_data.append({"tokens": new_tokens, "tags": new_tags})

    # --- FINAL REPORT AND SAVE ---
    if repair_count > 0:
        backup_path = file_path.replace('.json', '_backup.json')
        print(f"\n💾 Repaired {repair_count} examples.")
        print(f"   - Saving original data to '{backup_path}'")
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(original_data_copy, f, indent=2)
            
        print(f"   - Overwriting '{file_path}' with the repaired data.")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(repaired_data, f, indent=2)
    
    if error_count == 0 and repair_count == 0:
        print("\n✅ All checks passed. No errors found and no repairs needed.")
    elif error_count == 0 and repair_count > 0:
        print("\n✅ Repairs completed. No remaining logical errors were found.")
    else:
        print(f"\n❌ Found {error_count} unrecoverable errors that require manual review. Please check the messages above.")

if __name__ == "__main__":
    repair_and_validate('TrainingData.json')