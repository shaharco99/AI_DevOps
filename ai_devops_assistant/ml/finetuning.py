"""Local LLM Fine-Tuning Pipeline.

Provides utilities to fine-tune local LLMs using LoRA/QLoRA.

Supported frameworks:
- HuggingFace PEFT (Parameter-Efficient Fine-Tuning)
- HuggingFace Transformers

This module requires optional dependencies:
- transformers
- torch
- peft
- datasets

Example:
    >>> from ai_devops_assistant.ml.finetuning import FineTuner
    >>> finetuner = FineTuner(model_name="meta-llama/Llama-2-7b")
    >>> finetuner.prepare_dataset("path/to/training_data.json")
    >>> finetuner.train()
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FineTuningConfig:
    """Fine-tuning configuration."""

    model_name: str
    learning_rate: float = 2e-5
    num_epochs: int = 3
    batch_size: int = 8
    output_dir: str = "./finetuned_models"
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    use_qlora: bool = False
    max_seq_length: int = 2048
    gradient_accumulation_steps: int = 4


class FineTuningDataset:
    """Dataset preparation for fine-tuning."""

    def __init__(self, data_path: str):
        """Initialize dataset.

        Args:
            data_path: Path to training data
        """
        self.data_path = Path(data_path)
        self.data = []

    def load_json_lines(self) -> None:
        """Load JSONL format data.

        Expected format:
        {"text": "training example 1"}
        {"text": "training example 2"}
        """
        try:
            with open(self.data_path, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            self.data.append(data.get("text", data))
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping invalid JSON line: {line}")

            logger.info(f"Loaded {len(self.data)} examples from {self.data_path}")

        except FileNotFoundError:
            logger.error(f"Dataset file not found: {self.data_path}")

    def load_csv(self, text_column: str = "text") -> None:
        """Load CSV format data.

        Args:
            text_column: Name of column containing training text
        """
        try:
            import csv

            with open(self.data_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if text_column in row:
                        self.data.append(row[text_column])

            logger.info(f"Loaded {len(self.data)} examples from CSV")

        except ImportError:
            logger.error("CSV support requires csv library")
        except FileNotFoundError:
            logger.error(f"Dataset file not found: {self.data_path}")

    def validate(self) -> bool:
        """Validate dataset.

        Returns:
            True if valid, False otherwise
        """
        if not self.data:
            logger.error("Dataset is empty")
            return False

        if any(not isinstance(d, str) or not d.strip() for d in self.data):
            logger.error("Dataset contains empty or non-string entries")
            return False

        return True

    def get_data(self) -> list[str]:
        """Get dataset.

        Returns:
            List of training examples
        """
        return self.data


class FineTuner:
    """LLM fine-tuner using PEFT."""

    def __init__(self, config: FineTuningConfig):
        """Initialize fine-tuner.

        Args:
            config: FineTuningConfig object
        """
        self.config = config
        self.model = None
        self.tokenizer = None
        self.trainer = None

    def load_model(self) -> bool:
        """Load model and tokenizer.

        Returns:
            True if successful
        """
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading model: {self.config.model_name}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Load model
            if self.config.use_qlora:
                from transformers import BitsAndBytesConfig

                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype="float16",
                )

                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_name,
                    quantization_config=bnb_config,
                    device_map="auto",
                )
            else:
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.config.model_name,
                    device_map="auto",
                )

            # Apply LoRA
            self._apply_lora()

            return True

        except ImportError as e:
            logger.error(f"Missing required library: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False

    def _apply_lora(self) -> None:
        """Apply LoRA/QLoRA to model."""
        try:
            from peft import LoraConfig, get_peft_model

            lora_config = LoraConfig(
                r=self.config.lora_r,
                lora_alpha=self.config.lora_alpha,
                lora_dropout=self.config.lora_dropout,
                bias="none",
                task_type="CAUSAL_LM",
            )

            self.model = get_peft_model(self.model, lora_config)
            self.model.print_trainable_parameters()

        except ImportError:
            logger.error("PEFT library not installed")

    def prepare_dataset(self, data_path: str) -> bool:
        """Prepare training dataset.

        Args:
            data_path: Path to training data

        Returns:
            True if successful
        """
        try:
            dataset = FineTuningDataset(data_path)

            # Detect format from file extension
            if data_path.endswith(".jsonl"):
                dataset.load_json_lines()
            elif data_path.endswith(".csv"):
                dataset.load_csv()
            else:
                logger.error("Unsupported data format. Use .jsonl or .csv")
                return False

            if not dataset.validate():
                return False

            self.train_data = dataset.get_data()
            return True

        except Exception as e:
            logger.error(f"Error preparing dataset: {e}")
            return False

    def train(self) -> bool:
        """Fine-tune the model.

        Returns:
            True if successful
        """
        try:
            if self.model is None:
                logger.error("Model not loaded. Call load_model() first.")
                return False

            if not hasattr(self, "train_data") or not self.train_data:
                logger.error("Training data not prepared. Call prepare_dataset() first.")
                return False

            from datasets import Dataset
            from transformers import DataCollatorForLanguageModeling, Trainer,             TrainingArguments

            logger.info("Preparing training data...")

            # Create dataset
            dataset = Dataset.from_dict({"text": self.train_data})

            # Tokenize
            def tokenize_function(examples):
                return self.tokenizer(
                    examples["text"],
                    padding="max_length",
                    truncation=True,
                    max_length=self.config.max_seq_length,
                )

            tokenized_dataset = dataset.map(
                tokenize_function, batched=True, remove_columns=["text"]
            )

            # Create data collator
            data_collator = DataCollatorForLanguageModeling(
                self.tokenizer, mlm=False
            )

            # Training arguments
            training_args = TrainingArguments(
                output_dir=self.config.output_dir,
                num_train_epochs=self.config.num_epochs,
                per_device_train_batch_size=self.config.batch_size,
                gradient_accumulation_steps=self.config.gradient_accumulation_steps,
                learning_rate=self.config.learning_rate,
                save_strategy="epoch",
                logging_steps=10,
                warmup_steps=100,
                weight_decay=0.01,
            )

            # Create trainer
            trainer = Trainer(
                model=self.model,
                args=training_args,
                train_dataset=tokenized_dataset,
                data_collator=data_collator,
            )

            logger.info("Starting training...")
            trainer.train()

            # Save model
            self.save_model()

            return True

        except ImportError as e:
            logger.error(f"Missing required library: {e}")
            return False
        except Exception as e:
            logger.error(f"Error during training: {e}")
            return False

    def save_model(self) -> bool:
        """Save fine-tuned model.

        Returns:
            True if successful
        """
        try:
            output_dir = Path(self.config.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            self.model.save_pretrained(str(output_dir))
            self.tokenizer.save_pretrained(str(output_dir))

            # Save config
            config_path = output_dir / "finetuning_config.json"
            with open(config_path, "w") as f:
                json.dump(vars(self.config), f, indent=2, default=str)

            logger.info(f"Model saved to {output_dir}")
            return True

        except Exception as e:
            logger.error(f"Error saving model: {e}")
            return False

    def load_finetuned_model(self, model_path: str) -> bool:
        """Load a fine-tuned model.

        Args:
            model_path: Path to saved model

        Returns:
            True if successful
        """
        try:
            from peft import AutoPeftModelForCausalLM
            from transformers import AutoTokenizer

            logger.info(f"Loading fine-tuned model from {model_path}")

            self.model = AutoPeftModelForCausalLM.from_pretrained(model_path)
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)

            return True

        except Exception as e:
            logger.error(f"Error loading fine-tuned model: {e}")
            return False


def create_training_data_example(
    output_path: str, examples: list[str], format: str = "jsonl"
) -> bool:
    """Create example training data file.

    Args:
        output_path: Path to save training data
        examples: List of training examples
        format: Format (jsonl or csv)

    Returns:
        True if successful
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if format == "jsonl":
            with open(output_path, "w") as f:
                for example in examples:
                    json.dump({"text": example}, f)
                    f.write("\n")
        elif format == "csv":
            import csv

            with open(output_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["text"])
                writer.writeheader()
                for example in examples:
                    writer.writerow({"text": example})
        else:
            logger.error(f"Unsupported format: {format}")
            return False

        logger.info(f"Training data saved to {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error creating training data: {e}")
        return False
