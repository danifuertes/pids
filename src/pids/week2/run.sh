#!/usr/bin/env bash
# Train every available detection model by running train.ipynb with papermill.
# Only `model_name` is overridden; the rest of hyperparameters come from the notebook.
# Each executed notebook is saved next to its checkpoints: ../models/<model>/train.ipynb
# Re-running the script resumes each model from its last checkpoint.
#
# Usage:  ./run.sh                          # all models
#         ./run.sh ssd_v2 faster_rcnn_v3    # only the given ones
set -u

# Run from this folder so that local_path='../' in the notebook resolves correctly
cd "$(dirname "$0")"

# papermill lives in the pixi environment: re-launch this script inside it if needed
if ! command -v papermill >/dev/null; then
    if [ -z "${PIXI_ENVIRONMENT_NAME:-}" ] && command -v pixi >/dev/null; then
        exec pixi run bash "$(basename "$0")" "$@"
    fi
    echo "papermill not found: run 'pixi install' (or 'pip install papermill')"
    exit 1
fi

# papermill saves every tqdm refresh as a separate output. Merge them and keep only the
# last refresh of each bar, so every progress bar takes a single line in the notebook
squash_progress_bars() {
    python - "$1" <<'PY'
import re
import sys
import nbformat

path = sys.argv[1]
nb = nbformat.read(path, as_version=4)
for cell in nb.cells:
    if 'outputs' not in cell:
        continue
    outputs = []
    for out in cell.outputs:
        last = outputs[-1] if outputs else None
        if out.output_type == 'stream' and last and last.output_type == 'stream' and last.name == out.name:
            last.text += out.text
        else:
            outputs.append(out)
    for out in outputs:
        if out.output_type == 'stream':
            out.text = re.sub(r'.*\r(?=[^\n])', '', out.text)
    cell.outputs = outputs
nbformat.write(nb, path)
PY
}

# Same names as in torchvision_model() inside train.ipynb
MODELS=(
    faster_rcnn_v1
    faster_rcnn_v2
    faster_rcnn_v3
    retinanet_v1
    retinanet_v2
    ssd_v1
    ssd_v2
)
[ $# -gt 0 ] && MODELS=("$@")

failed=()
for model in "${MODELS[@]}"; do
    echo "===== Training ${model} ====="
    output="../models/${model}/train.ipynb"
    mkdir -p "../models/${model}"
    papermill train.ipynb "${output}" -p model_name "${model}" \
        || failed+=("${model}")
    [ -f "${output}" ] && squash_progress_bars "${output}"
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "Failed models: ${failed[*]}"
    exit 1
fi
echo "All models trained."
