# CRAFTS LoRA adapters

This directory documents the three role-specific LoRA adapters used by the
schema-critical CRAFTS agents. It does not currently contain model binaries.

The planned public assets are adapter-only releases. They do not contain Qwen
base-model weights, training records, benchmark requests, source diagrams,
evaluation references, optimizer state, scheduler state, experiment logs,
credentials, or private infrastructure metadata.

## Release status

The three checkpoints below are local release candidates. Their binary tensors
have been identified and hashed, but they have not yet been uploaded to this
repository.

Because the adapter tensors are approximately 0.35--0.65 GB each, the intended
distribution mechanism is a versioned GitHub Release rather than ordinary Git
objects. The repository will retain the model cards, loading documentation,
asset manifest, and checksums.

| Adapter | CRAFTS role | Required base model | LoRA rank | Tensor bytes | SHA-256 |
|---|---|---|---:|---:|---|
| `crafts-visual-descriptor-lora` | Visual Descriptor | `Qwen/Qwen3-VL-8B-Instruct` | 32 | 349,251,312 | `ceb159b0efb00ed3b438d97db848ae20036b1a598686a3f3eb24002d1d69e449` |
| `crafts-topology-lora` | Topology Agent | `Qwen/Qwen2.5-Coder-7B-Instruct` | 64 | 645,975,704 | `5390e741dd2ffd25384be44b4dabd48eff14541d8df5492687e5e0fec3924a01` |
| `crafts-specification-lora` | Specification Agent | `Qwen/Qwen2.5-Coder-7B-Instruct` | 64 | 645,975,704 | `c4c1f6cb4a03f8d20944df0d7d96cd7bf1c6defbb90f16eb103f7aa943044a22` |

The hashes above identify `adapter_model.safetensors` only. Release-archive
hashes will be added after the public metadata has been sanitized and the
archives have been assembled reproducibly.

## Adapter contents

Each release archive is planned to contain only the files required for
inference and verification:

```text
adapter_config.json
adapter_model.safetensors
README.md
SHA256SUMS
chat_template.jinja                 # when required by the selected checkpoint
tokenizer_config.json               # when required for compatibility
tokenizer.json                      # when required for compatibility
processor_config.json               # Visual Descriptor only
```

Internal filesystem locations in the training-time adapter metadata will be
replaced with the corresponding public base-model identifier before release.
This changes metadata only; it does not modify the adapter tensor file.

## Visual Descriptor adapter

- **Role:** convert permitted raster PFD evidence into `VisualGraphIR`.
- **Base model:** `Qwen/Qwen3-VL-8B-Instruct`.
- **Method:** PEFT LoRA, rank 32, alpha 64, dropout 0.05.
- **Target modules:** `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`,
  `up_proj`, and `down_proj`.
- **Selected checkpoint:** Visual v10-A r002, evaluation 16.
- **Selection:** validation token-weighted negative log likelihood with bounded
  early stopping.
- **Training boundary:** 197 training records and 16 validation records were
  read by this run; sealed test records were not read for training or
  checkpoint selection.

The adapter produces a perception artifact, not an executable topology.
VisualGraphIR must still pass its deterministic schema, identifier, endpoint,
geometry, evidence, and uncertainty checks. It must not be used to infer
unseen connections or to bypass topology validation.

## Topology Agent adapter

- **Role:** produce `TopologyIR` from accepted request evidence, optional
  `VisualGraphIR`, fixed chemical-engineering knowledge, and the verified
  capability contract.
- **Base model:** `Qwen/Qwen2.5-Coder-7B-Instruct`.
- **Method:** PEFT LoRA, rank 64, alpha 128, dropout 0.05.
- **Target modules:** `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`,
  `up_proj`, and `down_proj`.
- **Selected checkpoint:** epoch 3.
- **Selection:** teacher-forced validation loss.
- **Training boundary:** 5,000 training records and 1,000 validation records;
  no test record or test metric was used for checkpoint selection.

The adapter output is a candidate typed artifact. Unit identifiers, ports,
directed endpoints, thermodynamic compatibility, translators, terminals, and
graph consistency remain subject to deterministic validation.

## Specification Agent adapter

- **Role:** produce `SpecIR` from an accepted `TopologyIR`, grounded numerical
  requirements, fixed chemical-engineering knowledge, and the verified
  capability contract.
- **Base model:** `Qwen/Qwen2.5-Coder-7B-Instruct`.
- **Method:** PEFT LoRA, rank 64, alpha 128, dropout 0.05.
- **Target modules:** `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`,
  `up_proj`, and `down_proj`.
- **Selected checkpoint:** epoch 1.
- **Selection:** teacher-forced validation loss.
- **Training boundary:** 5,000 training records and 1,000 validation records;
  no test record was read for checkpoint selection.

The adapter does not guarantee numerical closure. Every target path, value,
unit, fixed/free role, duplicate assignment, and expected degree-of-freedom
intent must pass deterministic checks before compilation.

## Loading

Install compatible versions of PyTorch, Transformers, PEFT, Accelerate, and
Safetensors. The exact tested environment will be included in the release
manifest.

Text adapters can be loaded with the corresponding base model:

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base_id = "Qwen/Qwen2.5-Coder-7B-Instruct"
adapter_dir = "/path/to/crafts-topology-lora"

tokenizer = AutoTokenizer.from_pretrained(base_id)
base_model = AutoModelForCausalLM.from_pretrained(
    base_id,
    torch_dtype="auto",
    device_map="auto",
)
model = PeftModel.from_pretrained(base_model, adapter_dir)
model.eval()
```

For the Visual Descriptor, load `Qwen/Qwen3-VL-8B-Instruct` with the matching
multimodal processor and then attach the adapter through
`PeftModel.from_pretrained`. The release will include a tested loading script
so that processor and chat-template handling are not left implicit.

## Intended use

These adapters are intended only as components of the CRAFTS seven-role
workflow. They are designed for typed artifact generation inside the documented
visibility boundary and are not standalone process simulators.

Generated artifacts must be treated as untrusted until their deterministic
engineering gates pass. A successfully loaded adapter or schema-valid response
does not establish physical validity, numerical solvability, or optimization
feasibility.

## Out-of-scope use

The adapters are not intended for:

- safety-critical operation without independent engineering review;
- unrestricted process synthesis outside the verified simulator surface;
- direct equipment control;
- replacing thermodynamic, degree-of-freedom, initialization, or solver checks;
- reconstructing benchmark answers from evaluator-only material; or
- use without complying with the applicable base-model and repository terms.

## Data and evaluation boundary

Training data and OpenIDAES-450 records are not included with the weight
assets. OpenIDAES-450 is still being documented and audited for a later public
release.

The checkpoint-selection statements above describe the data-access and
selection procedure only. They are not standalone empirical performance claims.
System-level results require the complete seven-role workflow and its
deterministic execution gates.

## Licensing

The repository license does not replace the licenses or terms attached to the
Qwen base models. Users must obtain the compatible base model separately and
comply with its upstream terms.

CRAFTS-authored adapter and documentation files are distributed under the
repository's MIT License. The required Qwen base models are separately
distributed under the Apache License 2.0; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The base-model terms remain
applicable and base weights are not redistributed here.

## Integrity checks before upload

The public upload remains blocked until all of the following pass:

- the three tensor hashes match the selected local checkpoints;
- `adapter_config.json` contains a public base-model identifier and no private
  path;
- archive contents match the documented allowlist;
- no training record, benchmark record, log, optimizer state, credential, or
  private locator is present;
- each archive loads against its declared base model in an isolated smoke test;
- generated outputs still require the documented deterministic gates; and
- release assets, manifest, and checksums agree byte-for-byte.
