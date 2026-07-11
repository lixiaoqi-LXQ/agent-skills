# agent-skills

个人 Claude Code 技能仓库。集中登记自制 + 外部 skill，跨机器同步、每台机器保持独特性（GPU skill 只在 GPU 机开）。

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

## 用法

```bash
git clone git@github.com:lixiaoqi-LXQ/agent-skills.git ~/agent-skills
cd ~/agent-skills

./install.sh scan              # 扫描本机，输出分类 + 漂移报告（不改任何东西）
./install.sh init              # 首次：生成 local.yaml（已装的自动纳入，模糊的进报告）
./install.sh plan              # 打印 diff 计划，不执行
./install.sh apply             # 执行 diff（幂等）
./install.sh sync              # = init(若需) + apply（日常一键）
./install.sh sync --dry-run    # 只打印不执行
```

模糊类（普通目录、无 .git、非 symlink）脚本**只报告、永不自动改动**。归类判断（外部还是自制、找源）在 Claude Code 会话里用卡片完成，结果写回 catalog.yaml / local.yaml，再 `sync` 应用。

## 三类技能的安装方式
| 类别 | 安装 |
|---|---|
| homemade | `ln -s` 仓库 `skills/<name>` → `~/.claude/skills/<name>`；`git pull` 即更新 |
| git 外部 | `git clone --depth 1 <url>`（monorepo 用 `subdir` 走 sparse-checkout） |
| plugin 外部 | `claude plugin marketplace add` + `claude plugin install`（on/off = enable/disable） |

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
