#!/usr/bin/env bash
# agent-skills 安装/同步入口。薄启动器，逻辑全在 install.py（确定性引擎）。
# 用法：
#   ./install.sh scan           扫描本机，输出分类 + 漂移报告
#   ./install.sh init           生成 local.yaml（首次）
#   ./install.sh plan           打印 diff 计划
#   ./install.sh apply          执行 diff（幂等）
#   ./install.sh sync           = init(若需) + apply（日常一键）
#   ./install.sh sync --dry-run 只打印不执行
# 所有子命令支持 --target agents|claude|codex（默认 claude）。
# 设计见 docs/install-design.md。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[install] 找不到 $PY，请安装 Python 3。" >&2
  exit 1
fi

exec "$PY" "$DIR/install.py" "$@"
