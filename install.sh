#!/usr/bin/env bash
set -euo pipefail

# install.sh —— 按 local.yaml 把技能同步到本机 Claude Code。
# 逻辑尚在设计中，当前为骨架。详见 docs/install-design.md。

# ─── 1. 无 local.yaml → 扫描 + 交互式选择 ────────────────────────────────────
if [[ ! -f "$(dirname "$0")/local.yaml" ]]; then
  echo "[1/3] 未检测到 local.yaml：将扫描 catalog.yaml 并交互式让你选择要启用的技能。"
  echo "      （会基于 local.yaml.example 生成 local.yaml）"
  # TODO: 实现 —— 解析 catalog.yaml，列出 homemade + external，用 select/whiptail 交互，
  # TODO:           写出 local.yaml（selected / machine_local）。
else
  echo "[1/3] 已检测到 local.yaml，跳过交互式初始化。"
fi

# ─── 2. 有 local.yaml → 校验完整性、处理漂移 ─────────────────────────────────
echo "[2/3] 校验 local.yaml 中 selected 的条目在 catalog.yaml 中存在；"
echo "      检测 machine_local（手动安装、未进 catalog）的漂移。"
# TODO: 实现 —— 读 local.yaml + catalog.yaml 交叉校验：
# TODO:           - selected 中不存在的 name → 警告/移除
# TODO:           - 发现本地已装但未登记的 skill → 提示加入 machine_local
# TODO:           - external 条目的 source 可达性检查

# ─── 3. 按选择 diff 驱动地安装/卸载 ───────────────────────────────────────────
echo "[3/3] 根据 selected 与当前已装集合的 diff，安装/卸载技能。"
echo "      homemade: symlink 到 Claude Code skills 目录；external: 按 catalog 的 kind/source 装。"
# TODO: 实现 —— 计算 desired（selected ∪ machine_local）与 installed 的 diff：
# TODO:           - 新增 → homemade 用 ln -s，external 按 kind（plugin/marketplace/git）走对应安装器
# TODO:           - 移除 → 解除 symlink / 调用卸载
# TODO:           - 原子化、可重入、dry-run 模式
