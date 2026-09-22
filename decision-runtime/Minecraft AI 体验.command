#!/bin/zsh
set -eu
cd "${0:A:h}"
decision_python="$HOME/Library/Application Support/MinecraftDecisions/venv/bin/python"
if [[ ! -x "$decision_python" ]]; then
  print '没有找到已安装的 Minecraft AI 运行环境。'
  read '?按回车关闭。'
  exit 1
fi
exec "$decision_python" playground.py
