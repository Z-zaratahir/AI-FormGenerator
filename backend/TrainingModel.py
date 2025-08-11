# TrainingModel.py
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForTokenClassification, TrainingArguments, Trainer, DataCollatorForTokenClassification

def main():
    print("--- Loading Dataset ---")
    raw_datasets = load_dataset('json', data_files='TrainingData.json', split="train")

    print("--- Preparing Data for Training ---")
    model_checkpoint = "distilbert-base-uncased"
    tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)

    tags_list = sorted(list(set(tag for ex in raw_datasets for tag in ex['tags'])))
    tag2id = {tag: i for i, tag in enumerate(tags_list)}
    id2tag = {i: tag for i, tag in enumerate(tags_list)}

    def tokenize_and_align(examples):
        tokenized = tokenizer(examples["tokens"], truncation=True, is_split_into_words=True)
        labels = []
        for i, label in enumerate(examples["tags"]):
            word_ids = tokenized.word_ids(batch_index=i)
            prev_word_idx = None
            label_ids = []
            for word_idx in word_ids:
                if word_idx is None:
                    label_ids.append(-100)
                elif word_idx != prev_word_idx:
                    label_ids.append(tag2id[label[word_idx]])
                else:
                    label_ids.append(-100)
                prev_word_idx = word_idx
            labels.append(label_ids)
        tokenized["labels"] = labels
        return tokenized

    tokenized_datasets = raw_datasets.map(tokenize_and_align, batched=True)

    print("--- Setting up Trainer ---")
    model = AutoModelForTokenClassification.from_pretrained(
        model_checkpoint, num_labels=len(tags_list), id2label=id2tag, label2id=tag2id
    )
    data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)

    args = TrainingArguments(
        output_dir="form-generator-model-temp",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        num_train_epochs=3,
        weight_decay=0.01,
    )

    trainer = Trainer(
        model, args, train_dataset=tokenized_datasets, data_collator=data_collator, tokenizer=tokenizer
    )

    print("--- Starting Training ---")
    trainer.train()
    print("--- Training Complete ---")

    final_model_path = "./FormGeneratorModel"
    trainer.save_model(final_model_path)
    print(f"Model saved successfully to '{final_model_path}'")

if __name__ == "__main__":
    main()