# agent-skills 安装脚本设计

> 目标：跨机器同步 Claude Code skill 配置，同时保持每台机器的独特性（GPU skill 只在 GPU 机开启，存储机不装）。
> 引擎实现见 `install.py`，`install.sh` 是启动器。

## 1. 仓库结构

```
agent-skills/
├── catalog.yaml          # 【提交】技能总目录（homemade + external），跨机器共享的事实来源
├── local.yaml            # 【gitignore】本机选择（selected 开启项 + machine_local 本机独有发现）
├── local.yaml.example    # 【提交】local.yaml 样例
├── install.sh            # 启动器 → exec python3 install.py
├── install.py            # 引擎：扫描 / 分类 / diff-apply
├── skills/               # 自制 skill 源
│   └── <name>/SKILL.md
└── docs/install-design.md
```

两个配置文件的职责严格分离：

| 文件 | 提交？ | 职责 |
|---|---|---|
| `catalog.yaml` | ✅ | 全量已知技能清单（自制 + 外部）+ 安装元数据。所有机器共享。 |
| `local.yaml` | ❌ | 本机的选择：`selected`（开启哪些）+ `machine_local`（本机发现的、未进共享 catalog 的）。 |

## 2. catalog.yaml schema

```yaml
version: 1
homemade:
  - name: feishu-claude-bridge        # key，全 catalog 唯一
    path: skills/feishu-claude-bridge # 相对仓库根
    desc: 从飞书远控/通知本机 Claude Code
external:
  - name: frontend-slides
    kind: git                         # git | plugin
    url: https://github.com/zarazhangrui/frontend-slides.git
    # subdir: ...                     # 可选，monorepo 时 sparse-checkout 此子目录
    desc: HTML 演示文稿生成
  - name: nvidia-skills-perf-nsight-compute-analysis
    kind: git
    url: https://github.com/NVIDIA/skills.git
    subdir: plugins/nvidia-skills/skills/perf-nsight-compute-analysis
    desc: NCU 报告分析（monorepo 子目录，sparse-checkout）
  - name: superpowers                 # plugin 类示例
    kind: plugin
    marketplace: anthropics/claude-plugins-official   # github owner/repo 或 url
    plugin: superpowers               # plugin@marketplace 的 plugin 名
    desc: TDD/debugging 等工作流 skill 集
```

字段规则：
- `name` 是全 catalog 的唯一 key（homemade 和 external 之间也不能重名）。
- `kind`：homemade 无 kind（隐含）；external 必须是 `git` 或 `plugin`。
- git 类：`url` 必填；`subdir` 可选（monorepo 单 skill 子目录，走 sparse-checkout）。
- plugin 类：`marketplace`（来源）+ `plugin`（插件名）必填。

## 3. local.yaml schema

```yaml
selected:                # 开启的技能 name 列表（必须能在 catalog 或 machine_local 解析）
  - feishu-claude-bridge
machine_local:           # 本机发现的、未进共享 catalog 的技能
  - name: some-local-skill
    kind: git            # git | plugin | homemade-local
    url: https://...     # 或 marketplace/plugin 字段
    desc: ...
```

## 4. 两条不变量（脚本必须维护）

- **I1（已知性）**：本机已安装的每个 skill ∈ catalog ∪ local.machine_local。
  若违反（装了 catalog/machine_local 都没有的）→ 漂移，进入「漂移报告」流程。
- **I2（选择合法性）**：local.selected 的每个 name ∈ catalog ∪ local.machine_local。
  若违反（选了个不存在的）→ 警告并从 selected 剔除。

机器独特性靠 local.yaml 的 `selected` 体现：catalog 里列了 GPU skill，存储机的 local.yaml 不选它即可。

## 5. 分类决策树（扫描已装 skill 时）

扫描两个位置：
- `~/.claude/skills/<name>/`（自制 / git 外部 / 模糊）
- `claude plugin list --json`（plugin 外部）

```
一个已装 skill：
├─ 在 ~/.claude/skills/<name> 且是 symlink
│   ├─ 指向本仓库 skills/  → homemade（我们的）          [已知，归 catalog.homemade]
│   └─ 指向别处            → git 外部（被 link 进来）     [按 name 匹配 catalog.external]
├─ 在 ~/.claude/skills/<name> 且有 .git
│   └─ remote 可读         → git 外部                     [按 name 匹配 catalog.external]
├─ 出现在 plugin list --json (id = plugin@marketplace)
│   └─                     → plugin 外部                  [按 id 匹配 catalog.external kind=plugin]
└─ ~/.claude/skills/<name> 普通目录、无 .git、非 link
    └─                     → 模糊（ambiguous）            [进入漂移报告，不动它]
```

前三类可自动判定归属；只有「模糊」类落回人工。

## 6. 模糊类的处理（人工 + Claude）

模糊类（普通目录、无 .git、非 symlink）脚本**只报告、不改动**。判断由人（在本会话里由 Claude 用卡片问你）完成：

```
模糊 skill → 问用户：外部 还是 自制？
  ├─ 外部 → 找源（Claude 搜 GitHub 或用户提供 URL）→ 确认 → 写入 catalog.external（提交共享）
  │        （若源是 marketplace 格式且只要单 skill → 优先 git sparse-checkout 子目录，避免整装 150+ skill）
  └─ 自制 → 问「装进仓库吗?」→ 是 → copy 进 skills/ + 提交 + symlink
```

> 实测样本：本机 `ncu-cuda-profiling`、`nvidia-skills-perf-...` 都是普通目录，实际是外部 git clone（丢了 .git）。前者单仓库直接 clone；后者来自 `nvidia/skills` monorepo，走 sparse-checkout 子目录。

## 7. 三类技能的安装矩阵

| 类别 | 安装 | 更新 | 卸载 | on/off（diff-apply） |
|---|---|---|---|---|
| **homemade** | `ln -s` 仓库 `skills/<name>` → `~/.claude/skills/<name>` | `git pull`（仓库即源） | `rm` symlink | 建/删 symlink |
| **git 外部** | `git clone --depth 1 <url>` 进 `~/.claude/skills/<name>`（有 subdir 则 sparse-checkout 后只放子目录） | `git -C <name> pull` | `rm -rf` | clone / rm |
| **plugin 外部** | `claude plugin marketplace add <marketplace>` + `claude plugin install <plugin>@<marketplace>` | `claude plugin update <plugin>` | `claude plugin uninstall <plugin>` | `enable` / `disable` |

plugin 类**完全脚本化**（`claude plugin` CLI 非交互、有 `--json`/`--scope`），无需人工接力。

### monorepo 子目录（git + subdir）

`nvidia/skills` 这种一个仓库打包上百 skill 的，整 clone 太重。用 sparse-checkout 只取目标子目录：

```bash
git clone --depth 1 --filter=blob:none --sparse <url> <tmp>
git -C <tmp> sparse-checkout set <subdir>
mv <tmp>/<subdir> ~/.claude/skills/<name>
```

## 8. 状态机（install.py 子命令）

```
./install.sh scan    # 扫描本机，输出分类 + 漂移报告（text + JSON），不改任何东西
./install.sh init    # 交互式生成本机 local.yaml：已装固定开 / 自制默认开可关 / 外部逐一确认。非 TTY 则 homemade 开、外部关
./install.sh plan    # 计算 desired(selected ∪ machine_local) vs installed 的 diff，打印计划，不执行
./install.sh apply   # 执行 plan（幂等、可重入）。加 --dry-run 只打印不执行
./install.sh sync    # 日常一键：若无 local.yaml 先按默认生成，再 apply
```

全局 `--dry-run`：apply 只打印将要执行的命令，不改动。

### 执行流（sync）

1. **reconcile**：读 local.yaml + catalog.yaml + 扫描本机 → 检测漂移。
   - 装了未知 skill → 进漂移报告（模糊类原样报告；git/plugin 类能识别源就提示可登记）。
   - selected 里引用了不存在的 name → 警告 + 剔除（维护 I2）。
2. **diff**：`desired = selected ∪ machine_local`；`installed_ours = 我们管理的已装项`。
   - `desired \ installed` → 待安装。
   - `installed_ours \ desired` → 待卸载（**只动我们管的**：指向本仓库的 symlink、name 命中 catalog 的 git 目录、name 命中 catalog 的 plugin）。
3. **apply**：按矩阵执行安装/卸载。plugin 的 on/off 用 enable/disable，不重装。

### 「只管我们管的」原则（安全）

为避免误删用户手动装的东西，卸载仅在以下情况发生：
- symlink 且指向本仓库 `skills/`；
- `~/.claude/skills/<name>` 有 `.git` 且 name ∈ catalog.external(kind=git)；
- plugin id ∈ catalog.external(kind=plugin)。

**普通目录（模糊类）永远不碰**，哪怕 name 碰巧匹配。

## 9. 脚本 vs Claude 的分工

| 职责 | 归属 |
|---|---|
| 扫描、分类（决策树）、symlink/clone/plugin 调用、diff-apply、幂等 | **install.py**（确定性引擎） |
| 模糊类的「外部还是自制」判断、搜 GitHub 找源、确认 | **Claude + 用户**（本会话，用卡片交互） |
| 把判断结果持久化 | 写回 catalog.yaml（外部/自制）或 local.yaml（machine_local） |
| 应用持久化的结果 | 重跑 `install.sh sync` |

bash/python 不擅长搜网和模糊判断，所以这部分留给 Claude；判断落盘后，脚本负责确定性执行。两边职责干净。

## 10. 已知边角

- **同名冲突**：catalog 内 homemade/external name 必须唯一；`init`/`scan` 检测并报错。
- **plugin 打包多 skill**：plugin 类 on/off 粒度是整个 plugin（如 `nvidia-skills` 一次带 150+ skill）。只要单 skill 时，catalog 里登成 git+subdir 而非 plugin。
- **悬空引用**：catalog 删了某条（git pull 后），local.yaml 还引用 → reconcile 警告 + 剔除 + 卸载对应项。
- **PyYAML 依赖**：install.py 需要 PyYAML；缺失时自动 `pip install --user pyyaml` 并提示。
- **权限**：homemade 用 symlink 无需 sudo；plugin 走 `claude` CLI（user scope）无需 sudo。

## 11. 首次使用

```bash
git clone git@github.com:lixiaoqi-LXQ/agent-skills.git ~/agent-skills
cd ~/agent-skills
./install.sh init      # 生成 local.yaml（已装的自动纳入，模糊的进报告）
# 在 Claude Code 里：根据报告用卡片确认模糊类 → 写回 catalog/local.yaml
./install.sh sync      # 应用
```

之后日常：改 local.yaml 的 selected，或 `git pull` 后跑 `./install.sh sync`。
