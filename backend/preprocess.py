# text_processor.py
### Install Libraries
### -> pip install spacy
### -> python -m spacy download en_core_web_sm
### -> pip install emoji

import re
import string
import unicodedata
import spacy

# Load spaCy model once
nlp = spacy.load("en_core_web_sm")


def clean_text(text: str) -> str:
    """
    Clean the input text by:
      1. Unicode normalization
      2. Lowercasing
      3. Removing punctuation
      4. Replacing control characters with spaces
      5. Stripping out anything other than a–z, 0–9, and spaces (removes emojis)
      6. Collapsing whitespace
    """
    # 1. Normalize unicode
    text = unicodedata.normalize("NFKC", text)

    # 2. Lowercase
    text = text.lower()

    # 3. Remove punctuation (keeps letters, digits, spaces)
    text = ''.join(ch for ch in text if ch not in string.punctuation)

    # 4. Replace newlines and tabs with space
    text = text.replace("\n", " ").replace("\t", " ")

    # 5. Keep only a–z, 0–9, and spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)

    # 6. Collapse multiple spaces and trim
    text = ' '.join(text.split())

    return text


def tokenize_text(text: str) -> list[str]:
    """
    Tokenize the cleaned text using spaCy and return tokens.
    """
    doc = nlp(text)
    return [token.text for token in doc]


if __name__ == "__main__":
    sample = "Create   a form on AI!\nInclude 7 MCQs, ??2 short answers@     , and 1 file-upload xxf/gc///ggc .... 😀"
    cleaned = clean_text(sample)
    tokens = tokenize_text(cleaned)
    print("Cleaned:", cleaned)
    print("Tokens:", tokens)
