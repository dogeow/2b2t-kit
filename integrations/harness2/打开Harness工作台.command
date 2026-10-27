#!/bin/zsh
set -e
task_ui_dir="${0:A:h}"
exec "$task_ui_dir/../../../harness2/.venv/bin/python" "$task_ui_dir/ui.py" --open
