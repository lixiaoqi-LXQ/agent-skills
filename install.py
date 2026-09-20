#!/usr/bin/env python3
"""agent-skills 安装引擎。

把 catalog.yaml（共享清单）+ local.yaml（本机选择）描述的技能集，同步到本机
Agent 运行时（共享目录、Claude Code 或 Codex）。确定性、幂等、可重入。

设计见 docs/install-design.md。本文件只做确定性执行；模糊判断（搜源、外部/自制
归类）留给 Agent + 用户，结果落回 catalog.yaml / local.yaml，再重跑本脚本应用。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:
    print("[install] 缺少 PyYAML，尝试安装：pip install --user pyyaml", file=sys.stderr)
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "--user", "pyyaml"])
    if rc != 0:
        sys.exit("PyYAML 安装失败，请手动 `pip install --user pyyaml` 后重试。")
    import yaml  # type: ignore  # noqa: F811

# ─── 路径 ──────────────────────────────────────────────────────────────────────
REPO_DIR = Path(__file__).resolve().parent
CATALOG_PATH = REPO_DIR / "catalog.yaml"
LOCAL_PATH = REPO_DIR / "local.yaml"
SKILLS_SRC_DIR = REPO_DIR / "skills"
RUNTIME_TARGET = "claude"


def skills_dir_for(target: str, home: Path | None = None) -> Path:
    """返回目标运行时的 skill 目录；通用环境变量优先。"""
    generic = os.environ.get("AGENT_SKILLS_DIR")
    if generic:
        return Path(generic).expanduser()
    if target == "claude" and os.environ.get("CLAUDE_SKILLS_DIR"):
        return Path(os.environ["CLAUDE_SKILLS_DIR"]).expanduser()
    root = home or Path.home()
    roots = {
        "agents": root / ".agents" / "skills",
        "claude": root / ".claude" / "skills",
        "codex": root / ".codex" / "skills",
    }
    return roots[target]


SKILLS_DIR = skills_dir_for(RUNTIME_TARGET)


def configure_runtime(target: str) -> None:
    global RUNTIME_TARGET, SKILLS_DIR
    RUNTIME_TARGET = target
    SKILLS_DIR = skills_dir_for(target)


# ─── 加载配置 ──────────────────────────────────────────────────────────────────
def load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    homemade = {}
    for e in data.get("homemade") or []:
        if "name" in e:
            homemade[e["name"]] = e
    external = {}
    for e in data.get("external") or []:
        if "name" in e:
            external[e["name"]] = e
    # 同名冲突检测（homemade vs external）
    clash = set(homemade) & set(external)
    if clash:
        sys.exit(f"[catalog] name 同时出现在 homemade 和 external：{sorted(clash)}")
    return {"homemade": homemade, "external": external}


def load_local() -> dict | None:
    if not LOCAL_PATH.exists():
        return None
    with LOCAL_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    ml = {}
    for e in data.get("machine_local") or []:
        if "name" in e:
            ml[e["name"]] = e
    return {"selected": data.get("selected") or [], "machine_local": ml}


def write_local(selected: list[str], machine_local: dict) -> None:
    ml_list = [dict(v) for v in machine_local.values()]
    data = {"selected": selected, "machine_local": ml_list}
    with LOCAL_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


# ─── 解析：name → 安装规格 ────────────────────────────────────────────────────
def resolve(name: str, catalog: dict, local: dict | None) -> dict | None:
    """把一个 name 解析成安装规格 {kind, ...}。"""
    if name in catalog["homemade"]:
        e = catalog["homemade"][name]
        return {"kind": "homemade", "name": name, "path": REPO_DIR / e["path"]}
    if name in catalog["external"]:
        return {"kind": "external", "name": name, **catalog["external"][name]}
    if local and name in local["machine_local"]:
        e = local["machine_local"][name]
        kind = e.get("kind", "git")
        return {"kind": kind, "name": name, **e}
    return None


# ─── 扫描本机已装 ──────────────────────────────────────────────────────────────
def run_json(cmd: list[str]) -> list | dict:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def _git_remote(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
        ).decode().strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def scan_installed(catalog: dict) -> list[dict]:
    """扫描本机，分类每个已装技能。返回 list of dict。"""
    items: list[dict] = []
    seen_names: set[str] = set()

    # 1) 当前运行时的 skills 目录
    if SKILLS_DIR.exists():
        for p in sorted(SKILLS_DIR.iterdir()):
            if not p.name.startswith(".") and p.is_dir():
                name = p.name
                seen_names.add(name)
                if p.is_symlink():
                    target = Path(os.readlink(p))
                    if not target.is_absolute():
                        target = (SKILLS_DIR / target).resolve()
                    try:
                        target.relative_to(SKILLS_SRC_DIR.resolve())
                        ours = True
                    except ValueError:
                        ours = False
                    items.append({
                        "name": name, "kind": "homemade" if ours else "git",
                        "managed": ours or name in catalog["external"],
                        "source": str(target),
                        "detail": "symlink→repo" if ours else "symlink→external",
                    })
                elif (p / ".git").exists():
                    remote = _git_remote(p)
                    items.append({
                        "name": name, "kind": "git",
                        "managed": name in catalog["external"],
                        "source": remote or "(git, no remote)",
                        "detail": "git clone",
                    })
                else:
                    items.append({
                        "name": name, "kind": "ambiguous",
                        "managed": False,
                        "source": str(p),
                        "detail": "普通目录，无 .git，非 link（需人工归类）",
                    })

    # 2) Claude Code 独有的 plugin 系统
    plugin_entries = (
        run_json(["claude", "plugin", "list", "--json"])
        if RUNTIME_TARGET == "claude"
        else []
    )
    for entry in plugin_entries:
        pid = entry.get("id") or ""
        if "@" not in pid:
            continue
        plugin = pid.split("@", 1)[0]
        # name 优先用 catalog 里 id 匹配到的条目名；否则用 plugin 名
        cat_name = None
        for n, e in catalog["external"].items():
            if e.get("kind") == "plugin" and e.get("id") == pid:
                cat_name = n
                break
        name = cat_name or plugin
        items.append({
            "name": name, "kind": "plugin",
            "managed": cat_name is not None,
            "source": pid,
            "enabled": entry.get("enabled", True),
            "detail": f"plugin {pid} ({'on' if entry.get('enabled', True) else 'off'})",
        })
    return items


# ─── 安装/卸载原语 ─────────────────────────────────────────────────────────────
def sh(cmd: list[str], dry: bool, check: bool = True) -> int:
    print("  $ " + " ".join(cmd))
    if dry:
        return 0
    rc = subprocess.call(cmd)
    if check and rc != 0:
        raise SystemExit(f"[!] 命令失败 (rc={rc})：{' '.join(cmd)}")
    return rc


def install_one(spec: dict, dry: bool) -> None:
    kind = spec["kind"]
    name = spec["name"]
    dest = SKILLS_DIR / name
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    if kind == "homemade":
        src = Path(spec["path"])
        if not src.exists():
            raise SystemExit(f"[!] 自制 skill 源不存在：{src}")
        if dest.exists() or dest.is_symlink():
            sh(["rm", "-rf", str(dest)], dry)
        sh(["ln", "-s", str(src), str(dest)], dry)

    elif kind == "git":
        url = spec["url"]
        subdir = spec.get("subdir")
        if dest.exists() or dest.is_symlink():
            print(f"  ~ {name} 已存在，跳过 clone（如需重装请先移除 {dest}）")
            return
        if subdir:
            tmp = Path(tempfile.mkdtemp(prefix=f"agent-skills-{name}-"))
            try:
                sh(["git", "clone", "--depth", "1", "--filter=blob:none",
                    "--sparse", url, str(tmp)], dry)
                sh(["git", "-C", str(tmp), "sparse-checkout", "set", subdir], dry)
                sub_src = tmp / subdir
                if not sub_src.exists():
                    raise SystemExit(f"[!] 子目录不存在：{sub_src}")
                sh(["mv", str(sub_src), str(dest)], dry)
            finally:
                if not dry:
                    shutil.rmtree(tmp, ignore_errors=True)
        else:
            sh(["git", "clone", "--depth", "1", url, str(dest)], dry)

    elif kind == "plugin":
        if RUNTIME_TARGET != "claude":
            raise SystemExit("[!] plugin 安装仅支持 Claude Code 目标")
        mp = spec.get("marketplace")
        pid = spec.get("id") or f"{name}@{mp}"
        if mp:
            # 幂等：marketplace add 容忍「已存在」
            sh(["claude", "plugin", "marketplace", "add", mp], dry, check=False)
        sh(["claude", "plugin", "install", pid], dry, check=False)
    else:
        raise SystemExit(f"[!] 未知 kind：{kind}")


def remove_one(item: dict, dry: bool) -> None:
    """移除一个「我们管的」已装项。"""
    kind = item["kind"]
    name = item["name"]
    if kind == "homemade" or kind == "git":
        dest = SKILLS_DIR / name
        sh(["rm", "-rf", str(dest)], dry)
    elif kind == "plugin":
        if RUNTIME_TARGET != "claude":
            return
        # on/off 语义：deselect → disable（不 uninstall，保留可再开）
        sh(["claude", "plugin", "disable", item["source"].split("@")[0]], dry, check=False)


def enable_plugin(spec: dict, dry: bool) -> None:
    if RUNTIME_TARGET != "claude":
        return
    pid = spec.get("id") or spec["name"]
    sh(["claude", "plugin", "enable", pid.split("@")[0]], dry, check=False)


# ─── 子命令 ────────────────────────────────────────────────────────────────────
def cmd_scan(args) -> int:
    catalog = load_catalog()
    local = load_local()
    ml_names = set((local or {}).get("machine_local", {}))
    items = scan_installed(catalog)
    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    print(f"=== 扫描结果（target: {RUNTIME_TARGET}, skills dir: {SKILLS_DIR}）===\n")
    managed = [i for i in items if i["managed"]]
    ml_items = [i for i in items if (not i["managed"]) and i["name"] in ml_names]
    drift = [i for i in items if (not i["managed"]) and i["name"] not in ml_names]
    for tag, group in [("已纳管 (catalog)", managed),
                       ("本机登记 (machine_local)", ml_items),
                       ("漂移 (未登记)", drift)]:
        if not group:
            continue
        print(f"── {tag} ──")
        for i in group:
            star = "✓" if i["managed"] else ("~" if i["name"] in ml_names else "?")
            print(f"  {star} {i['name']:<45} {i['kind']:<10} {i['source']}")
        print()
    if drift:
        print("[!] 漂移项需人工归类（外部→找源登记 catalog；自制→问是否装进仓库）。")
        print("    模糊（ambiguous）项脚本永不自动改动。")
    return 0


def ensure_local(catalog: dict) -> dict:
    """无 local.yaml 时，按扫描生成一份（homemade 默认 on + 已装 catalog external on）。"""
    if LOCAL_PATH.exists():
        local = load_local()
        if local is None:  # 空文件等异常情况
            local = {"selected": [], "machine_local": {}}
            write_local([], {})
        return local
    items = scan_installed(catalog)
    installed_names = {i["name"] for i in items if i["managed"]}
    selected = list(catalog["homemade"].keys())  # homemade 默认全开
    for n in catalog["external"]:
        if n in installed_names:
            selected.append(n)
    write_local(selected, {})
    print(f"[init] 已生成 {LOCAL_PATH}（selected={len(selected)}）")
    return {"selected": selected, "machine_local": {}}


def _parse_indices(ans: str, n: int) -> set[int]:
    """把 "1,3" 解析成 0-based 下标集合；越界/非法忽略。"""
    out: set[int] = set()
    for tok in ans.replace("，", ",").split(","):
        tok = tok.strip()
        if tok.isdigit():
            i = int(tok) - 1
            if 0 <= i < n:
                out.add(i)
    return out


def interactive_init(catalog: dict, items: list[dict]) -> list[str]:
    """TTY 交互式生成 selected。分三段：
    (A) 已安装 → 固定开启，仅展示；
    (B) 自制未装 → 默认开，可选关闭；
    (C) 外部未装 → 默认关，逐一确认。"""
    installed_managed = {i["name"] for i in items if i["managed"]}
    installed_any = {i["name"] for i in items}
    selected: set[str] = set(installed_managed)  # (A) 固定开

    if installed_managed:
        print("\n[已安装 · 固定开启]")
        for n in sorted(installed_managed):
            print(f"  • {n}")

    # (B) 自制未装：默认开，可关
    b = [n for n in catalog["homemade"] if n not in installed_any]
    if b:
        print("\n[自制 skill · 默认开启，可选关闭]")
        for i, n in enumerate(b, 1):
            print(f"  {i}. {n} — {catalog['homemade'][n].get('desc', '')}")
        ans = input("  输入要【关闭】的序号（逗号分隔，回车=全部保留）> ").strip()
        off = _parse_indices(ans, len(b))
        for i, n in enumerate(b):
            if i not in off:
                selected.add(n)
            else:
                print(f"  ✗ 关闭 {n}")

    # (C) 外部未装：逐一确认
    c = [n for n in catalog["external"] if n not in installed_any]
    if c:
        print("\n[外部 skill · 默认关闭，逐一确认]")
        for n in c:
            e = catalog["external"][n]
            extra = e.get("url") or e.get("id") or ""
            print(f"  · {n} [{e.get('kind', '')}] {extra}")
            print(f"    {e.get('desc', '')}")
            ans = input("    启用? [y/N] > ").strip().lower()
            if ans == "y":
                selected.add(n)
    return sorted(selected)


def build_plan(catalog: dict, local: dict) -> dict:
    """计算 diff。返回 {to_install, to_remove, to_enable, warnings, drift}。"""
    items = scan_installed(catalog)
    installed_by_name = {}
    for i in items:
        # plugin 可能用 plugin 名作 name（未在 catalog 时）；纳管的用 catalog name
        installed_by_name[i["name"]] = i

    desired_names = list(local["selected"]) + list(local["machine_local"].keys())

    # I2：selected/machine_local 引用必须可解析
    warnings = []
    valid_desired = []
    for n in desired_names:
        spec = resolve(n, catalog, local)
        if spec is None:
            warnings.append(f"selected/machine_local 引用了未知技能：{n}（已剔除）")
        elif spec["kind"] == "plugin" and RUNTIME_TARGET != "claude":
            warnings.append(
                f"{n} 是 Claude plugin，仅支持 Claude Code；当前 {RUNTIME_TARGET} 目标已跳过"
            )
        else:
            valid_desired.append(n)
    desired_set = set(valid_desired)

    # 漂移：已装但未纳管（不在 catalog 也不在 machine_local）
    drift = []
    for i in items:
        if i["managed"]:
            continue
        # 是否被 local.machine_local 覆盖？
        if i["name"] in local["machine_local"]:
            continue
        drift.append(i)

    to_install, to_enable = [], []
    for n in sorted(desired_set):
        spec = resolve(n, catalog, local)  # type: ignore[arg-type]
        inst = installed_by_name.get(n)
        if inst is None:
            to_install.append(spec)
        elif spec and spec["kind"] == "plugin" and not inst.get("enabled", True):
            to_enable.append(spec)
        # homemade/git 若已装则无操作

    to_remove = []
    for i in items:
        if not i["managed"]:
            continue  # 不是我们管的，绝不碰
        if i["name"] in desired_set:
            continue
        # 纳管但未 desired → 移除/禁用
        to_remove.append(i)

    return {
        "to_install": to_install, "to_remove": to_remove,
        "to_enable": to_enable, "warnings": warnings, "drift": drift,
    }


def print_plan(plan: dict) -> None:
    if plan["warnings"]:
        print("── 警告 ──")
        for w in plan["warnings"]:
            print(f"  ! {w}")
        print()
    if plan["to_install"]:
        print("── 待安装 ──")
        for s in plan["to_install"]:
            extra = s.get("url") or s.get("id") or s.get("path", "")
            print(f"  + {s['name']:<30} {s['kind']:<8} {extra}")
        print()
    if plan["to_enable"]:
        print("── 待启用（plugin）──")
        for s in plan["to_enable"]:
            print(f"  ⏻ {s['name']}")
        print()
    if plan["to_remove"]:
        print("── 待移除/禁用 ──")
        for i in plan["to_remove"]:
            print(f"  - {i['name']:<30} {i['kind']}")
        print()
    if plan["drift"]:
        print("── 漂移（需人工归类，本次不处理）──")
        for i in plan["drift"]:
            print(f"  ? {i['name']:<45} {i['kind']:<10} {i['source']}")
        print()
    if not (plan["to_install"] or plan["to_remove"] or plan["to_enable"]):
        print("（无变更，已是期望态）")


def cmd_init(args) -> int:
    catalog = load_catalog()
    if LOCAL_PATH.exists():
        print(f"[init] {LOCAL_PATH} 已存在，跳过。如需重建请先删除它。")
        local = load_local() or {"selected": [], "machine_local": {}}
        print_plan(build_plan(catalog, local))
        return 0

    items = scan_installed(catalog)
    tty = sys.stdin.isatty() and sys.stdout.isatty()
    if not args.no_interactive and tty:
        print("=== agent-skills 初始化（交互式）===\n")
        selected = interactive_init(catalog, items)
    elif args.no_interactive:
        print("[init] --no-interactive：homemade 默认开，外部默认关。")
        installed_managed = {i["name"] for i in items if i["managed"]}
        selected = sorted(set(catalog["homemade"]) | installed_managed)
    else:
        print("[init] 非交互终端（无 TTY）：homemade 默认开，外部默认关。")
        print("      需要 TTY 才能交互选择；或手动编辑 local.yaml。")
        installed_managed = {i["name"] for i in items if i["managed"]}
        selected = sorted(set(catalog["homemade"]) | installed_managed)
    write_local(selected, {})
    print(f"\n[init] 已生成 {LOCAL_PATH}（selected={len(selected)}）")
    local = {"selected": selected, "machine_local": {}}
    plan = build_plan(catalog, local)
    print_plan(plan)
    return 0


def cmd_plan(args) -> int:
    catalog = load_catalog()
    local = load_local()
    if local is None:
        print("[plan] 无 local.yaml，请先 `./install.sh init`。")
        return 1
    plan = build_plan(catalog, local)
    print_plan(plan)
    return 0


def cmd_apply(args) -> int:
    catalog = load_catalog()
    local = load_local()
    if local is None:
        print("[apply] 无 local.yaml，请先 `./install.sh init`。")
        return 1
    plan = build_plan(catalog, local)
    print_plan(plan)
    if args.dry_run:
        print("[dry-run] 未执行任何改动。")
        return 0
    if not (plan["to_install"] or plan["to_remove"] or plan["to_enable"]):
        return 0
    print("=== 执行 ===")
    for spec in plan["to_install"]:
        print(f"[+] 安装 {spec['name']} ({spec['kind']})")
        install_one(spec, args.dry_run)
    for spec in plan["to_enable"]:
        print(f"[⏻] 启用 {spec['name']}")
        enable_plugin(spec, args.dry_run)
    for item in plan["to_remove"]:
        print(f"[-] 移除 {item['name']} ({item['kind']})")
        remove_one(item, args.dry_run)
    print("=== 完成 ===")
    return 0


def cmd_sync(args) -> int:
    catalog = load_catalog()
    local = ensure_local(catalog)  # 无则生成；有则加载
    plan = build_plan(catalog, local)
    print_plan(plan)
    if args.dry_run:
        print("[dry-run] 未执行任何改动。")
        return 0
    if not (plan["to_install"] or plan["to_remove"] or plan["to_enable"]):
        return 0
    print("=== 执行 ===")
    for spec in plan["to_install"]:
        print(f"[+] 安装 {spec['name']} ({spec['kind']})")
        install_one(spec, args.dry_run)
    for spec in plan["to_enable"]:
        print(f"[⏻] 启用 {spec['name']}")
        enable_plugin(spec, args.dry_run)
    for item in plan["to_remove"]:
        print(f"[-] 移除 {item['name']} ({item['kind']})")
        remove_one(item, args.dry_run)
    print("=== 完成 ===")
    return 0


# ─── CLI ───────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        prog="install.sh", description="agent-skills 同步引擎")
    # --dry-run 通过 parent 挂到每个子命令，便于 `sync --dry-run` 这样的顺序。
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("-n", "--dry-run", action="store_true", help="只打印，不改动")
    parent.add_argument(
        "--target",
        choices=("agents", "claude", "codex"),
        default=os.environ.get("AGENT_SKILLS_TARGET", "claude"),
        help="安装目标（默认 claude；agents 为跨运行时共享目录）",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", parents=[parent], help="扫描本机，输出分类 + 漂移报告")
    p_scan.add_argument("--json", action="store_true", help="JSON 输出")
    p_scan.set_defaults(func=cmd_scan)

    p_init = sub.add_parser("init", parents=[parent], help="生成本机 local.yaml（交互式选择要开启的 skill）")
    p_init.add_argument("--no-interactive", action="store_true", help="不交互：homemade 默认开、外部默认关")
    p_init.set_defaults(func=cmd_init)
    sub.add_parser("plan", parents=[parent], help="打印 diff 计划，不执行").set_defaults(func=cmd_plan)
    sub.add_parser("apply", parents=[parent], help="执行 diff").set_defaults(func=cmd_apply)
    sub.add_parser("sync", parents=[parent], help="= init(若需) + apply").set_defaults(func=cmd_sync)

    args = ap.parse_args()
    configure_runtime(args.target)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
