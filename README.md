# agent-skills

个人 Agent 技能仓库。集中登记自制 + 外部 skill，在 Claude Code、Codex 与兼容 `~/.agents/skills` 的工具之间跨机器同步，同时保留每台机器的独特选择（例如 GPU skill 只在 GPU 机开启）。

完整设计见 [`docs/install-design.md`](docs/install-design.md)。

## 目录结构

```
agent-skills/
├── catalog.yaml           # 【提交】技能总目录（homemade + external），跨机器共享的事实来源
├── local.yaml             # 【gitignore】本机选择：selected（开启）+ machine_local（本机独有）
├── local.yaml.example     # local.yaml 样例（提交）
├── install.sh             # 入口（启动器 → install.py）
├── install.py             # 同步引擎：扫描 / 分类 / diff-apply（确定性、幂等）
├── skills/                # 自制 skill 源
│   └── <name>/SKILL.md
└── docs/install-design.md
```

### catalog.yaml vs local.yaml
| 文件 | 提交 | 作用 |
|---|---|---|
| `catalog.yaml` | ✅ | 全量已知技能清单（homemade + external）+ 安装元数据。所有机器共享。 |
| `local.yaml` | ❌ | 本机选择：`selected`（开启哪些）+ `machine_local`（本机发现、未进 catalog 的）。机器独特性靠它。 |

## 两条不变量
1. **已知性**：本机已装的每个 skill ∈ catalog ∪ local.machine_local。违反 → 漂移报告。
2. **选择合法**：local.selected 的每个 name ∈ catalog ∪ local.machine_local。违反 → 警告 + 剔除。

## 首次使用（新机器 clone 后）

仓库路径随意，不绑定 `~/agent-skills`（脚本按自身位置定位 catalog/skills）。

```bash
git clone git@github.com:lixiaoqi-LXQ/agent-skills.git ~/agent-skills   # 路径随意
cd ~/agent-skills
./install.sh init --target agents   # 交互式生成本机 local.yaml（见下）
./install.sh sync --target agents   # 应用：symlink 自制、clone git 外部
```

`init` 会进交互式选择，分三段：
1. **已安装** → 固定开启（仅展示，不可选）；
2. **自制 skill** → 默认开启，可输入序号关闭；
3. **外部 skill** → 默认关闭，逐一确认 `[y/N]`（每条显示来源与描述）。

> 这就是「机器独特性」的落点：同一份 catalog，每台机器在 `init` 时勾选自己要的；GPU 机开 GPU skill，存储机不开。结果写到 gitignored 的 `local.yaml`。
>
> 非 TTY（管道/脚本）环境 `init` 不交互，默认 homemade 开、外部关；可手动编辑 `local.yaml` 后 `sync`。

## 命令一览

```bash
./install.sh scan              # 扫描本机：分类（catalog / machine_local / 漂移）+ 漂移报告，不改任何东西
./install.sh init              # 生成/刷新本机 local.yaml（交互式选要开的 skill）
./install.sh init --no-interactive   # 非交互：homemade 默认开、外部默认关
./install.sh plan              # 打印 diff 计划，不执行
./install.sh apply             # 执行 diff（幂等、可重入）
./install.sh sync              # 日常一键：若无 local.yaml 先按默认生成，再 apply
./install.sh sync --dry-run    # 只打印不执行
```

所有命令均支持 `--target agents|claude|codex`：

| target | 目录 | 说明 |
|---|---|---|
| `agents` | `~/.agents/skills` | 推荐；Claude Code、Codex 等支持该约定的工具可共享 |
| `claude` | `~/.claude/skills` | 默认值，兼容旧用法；额外管理 Claude plugin |
| `codex` | `~/.codex/skills` | Codex 专用目录 |

可用 `AGENT_SKILLS_TARGET` 设置默认 target，用 `AGENT_SKILLS_DIR` 覆盖目标目录。旧的 `CLAUDE_SKILLS_DIR` 在 `claude` target 下继续有效。Claude plugin 没有跨运行时安装格式，因此在 `agents`/`codex` target 下会被明确跳过并给出提示。

模糊类（普通目录、无 .git、非 symlink）脚本**只报告、永不自动改动**。归类判断（外部还是自制、找源）由 Agent 与用户确认，结果写回 catalog.yaml / local.yaml，再 `sync` 应用。

## 日常维护

- 开/关某 skill：编辑本机 `local.yaml` 的 `selected`，再 `./install.sh sync`。
- 拉新 catalog：`git pull` → `./install.sh sync`（新增的自制/外部会按 `init` 规则处理；若想重新交互选，删 `local.yaml` 再 `init`）。
- 仓库搬家：homemade symlink 存绝对路径，搬家后会失效；从新位置重跑 `./install.sh sync` 刷新即可。
- 换运行时：`./install.sh sync --target agents|claude|codex`。
- 覆盖安装目录：`AGENT_SKILLS_DIR=/path ./install.sh sync --target agents`。

## 三类技能的安装方式
| 类别 | 安装 |
|---|---|
| homemade | `ln -s` 仓库 `skills/<name>` → 当前 target 的 skills 目录；`git pull` 即更新 |
| git 外部 | `git clone --depth 1 <url>`（monorepo 用 `subdir` 走 sparse-checkout） |
| plugin 外部 | 仅 `claude` target：`claude plugin marketplace add` + `claude plugin install`（on/off = enable/disable） |

## 新增自制 skill
1. 在 `skills/<name>/` 写 `SKILL.md`（YAML frontmatter: `name`, `description`）。
2. `catalog.yaml` 的 `homemade` 加一条：`name` / `path` / `desc`。
3. 本机 `local.yaml` 的 `selected` 加上 name（init 默认会选所有 homemade）。
4. `./install.sh sync`。

## 登记外部 skill
在 `catalog.yaml` 的 `external` 加一条：

```yaml
# git 类
- name: frontend-slides
  kind: git
  url: https://github.com/zarazhangrui/frontend-slides.git
  # subdir: path/to/skill      # monorepo 时 sparse-checkout 此子目录
  desc: ...

# plugin 类
- name: superpowers
  kind: plugin
  marketplace: anthropics/claude-plugins-official   # `marketplace add` 的源
  id: superpowers@claude-plugins-official           # install + list 匹配用
  desc: ...
```
加进本机 `local.yaml` 的 `selected`，再 `sync`。
