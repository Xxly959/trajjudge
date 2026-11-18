"""Exercise TRL data preparation on two synthetic rows with tool interactions."""

import argparse
from copy import deepcopy
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_training_candidates import validate_conversation


TEMPLATE = """{%- if tools %}tools {{ tools | tojson }}{{ '\n' }}{% endif -%}
{%- for m in messages %}{{ m.role }} {{ m.content or '' }}
{%- if m.tool_calls %}{% for c in m.tool_calls %} call {{ c.function.name }} {{ c.function.arguments | tojson }}{% endfor %}{% endif %}
{%- if m.role == 'tool' %} result {{ m.name }} {{ m.tool_call_id }}{% endif %}{{ '\n' }}
{%- endfor %}{% if add_generation_prompt %}assistant {% endif %}"""


def samples():
    prompt = [{"role": "user", "content": "Inspect the synthetic result."}]
    tools = [{"type": "function", "function": {
        "name": "inspect", "description": "Inspect a synthetic JSON file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }}]
    call = {"role": "assistant", "tool_calls": [
        {"id": "demo-1", "type": "function", "function": {"name": "inspect", "arguments": {"path": "result.json"}}},
    ]}

    def completion(status):
        return [call, {"role": "tool", "name": "inspect", "tool_call_id": "demo-1", "content": status},
                {"role": "assistant", "content": f"Observed {status}."}]

    sft = {"messages": prompt + completion("accepted"), "tools": tools}
    preference = {"prompt": prompt, "chosen": completion("accepted"), "rejected": completion("rejected"), "tools": tools}
    return sft, preference


def verify(output):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from datasets import Dataset, disable_progress_bars
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast
    from trl import DPOConfig, DPOTrainer, SFTConfig, SFTTrainer

    disable_progress_bars()
    output.mkdir(parents=True)
    sft, preference = samples()
    datasets = {}
    for kind, row in (("sft", sft), ("preferences", preference)):
        path = output / f"{kind}.jsonl"
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        datasets[kind] = Dataset.from_list([loaded], on_mixed_types="use_json")
    sft_row, dpo_row = datasets["sft"][0], datasets["preferences"][0]
    validate_conversation(sft_row["messages"], sft_row["tools"])
    for side in ("chosen", "rejected"):
        validate_conversation(dpo_row["prompt"] + dpo_row[side], dpo_row["tools"])
    words = ["[UNK]", "[PAD]", "[EOS]", "user", "assistant", "tool", "inspect", "accepted", "rejected", "demo"]
    raw = Tokenizer(WordLevel(dict(zip(words, range(len(words)))), unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=raw, unk_token="[UNK]", pad_token="[PAD]",
                                       eos_token="[EOS]", chat_template=TEMPLATE)
    rendered = tokenizer.apply_chat_template(sft_row["messages"], tools=sft_row["tools"], tokenize=False)
    if any(marker not in rendered for marker in ('call inspect', '"path": "result.json"', "result inspect demo-1")):
        raise ValueError("chat template lost tool information")

    def model():
        config = GPT2Config(vocab_size=len(tokenizer), n_layer=1, n_head=1, n_embd=8, n_positions=512,
                            eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id)
        return GPT2LMHeadModel(config)

    common = {"use_cpu": True, "bf16": False, "report_to": "none",
              "disable_tqdm": True, "per_device_train_batch_size": 1}
    sft_trainer = SFTTrainer(model(), args=SFTConfig(output_dir=str(output / "sft-trainer"), max_length=None, **common),
                             train_dataset=datasets["sft"], processing_class=tokenizer)
    policy = model()
    dpo_trainer = DPOTrainer(policy, ref_model=deepcopy(policy),
                             args=DPOConfig(output_dir=str(output / "dpo-trainer"), max_length=256, **common),
                             train_dataset=datasets["preferences"], processing_class=tokenizer)
    sft_ids = sft_trainer.train_dataset[0]["input_ids"]
    dpo = dpo_trainer.train_dataset[0]
    if not sft_ids or not dpo["prompt_ids"] or dpo["chosen_ids"] == dpo["rejected_ids"]:
        raise ValueError("trainer preprocessing did not preserve both outcomes")
    record = {
        "schema_version": 1, "source": "synthetic_format_fixture",
        "versions": {name: version(name) for name in ("datasets", "transformers", "trl", "torch", "jinja2")},
        "sft": {"rows": len(sft_trainer.train_dataset), "tokens": len(sft_ids), "max_length": None},
        "preference": {"rows": len(dpo_trainer.train_dataset), "prompt_tokens": len(dpo["prompt_ids"]),
                       "chosen_tokens": len(dpo["chosen_ids"]), "rejected_tokens": len(dpo["rejected_ids"])},
        "tool_calls_round_trip": True, "training_run": False,
    }
    (output / "format.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TRL preprocessed one synthetic SFT row and one synthetic preference pair")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    verify(parser.parse_args().output)
