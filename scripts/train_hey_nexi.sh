#!/usr/bin/env bash
# Train a real "hey nexi" openWakeWord model.
# RUN ON A GPU — Google Colab (GPU runtime) is strongly recommended because it
# also auto-downloads the negative/background datasets referenced below.
# Local run needs Python 3.10+, CUDA PyTorch, and those datasets fetched manually.
set -euo pipefail

# ── 1. Dependencies ────────────────────────────────────────────────────────
pip install openwakeword piper-phonemize torch
git clone https://github.com/dscripka/openWakeWord
git clone https://github.com/rhasspy/piper-sample-generator

# ── 2. A Piper TTS voice to synthesize the "hey nexi" samples ───────────────
mkdir -p piper-sample-generator/models
wget -O piper-sample-generator/models/en_US-libritts_r-medium.pt \
  https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt

# ── 3. Training config ─────────────────────────────────────────────────────
# NOTE: background_paths + feature_data_files point at large datasets the Colab
# notebook downloads automatically (AudioSet/FMA negatives, ACAV100M features,
# validation features). Fetch them per openWakeWord's docs if running locally.
cat > hey_nexi.yaml <<'YAML'
target_phrase: ["hey nexi"]
model_name: hey_nexi
n_samples: 40000          # synthetic "hey nexi" clips (more = better)
n_samples_val: 2000
steps: 50000              # training steps
target_accuracy: 0.7
target_recall: 0.5
output_dir: ./hey_nexi_model
tts_batch_size: 50
augmentation_rounds: 1
background_paths: ["./audioset_16k", "./fma_16k"]              # noise for augmentation
false_positive_validation_data_path: "./validation_set_features.npy"
feature_data_files:
  ACAV100M_sample: "./openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
YAML

# ── 4. Train (three stages) ────────────────────────────────────────────────
cd openWakeWord
python openwakeword/train.py --training_config ../hey_nexi.yaml --generate_clips
python openwakeword/train.py --training_config ../hey_nexi.yaml --augment_clips
python openwakeword/train.py --training_config ../hey_nexi.yaml --train_model

# ── 5. Result ──────────────────────────────────────────────────────────────
# Output model: hey_nexi_model/hey_nexi.onnx
# Copy it to your NEXI repo:  models/hey_nexi.onnx  (overwrite the broken one)
echo "Done. Copy hey_nexi_model/hey_nexi.onnx -> <nexi>/models/hey_nexi.onnx"
