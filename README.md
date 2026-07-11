# agent-skills

个人 Claude Code 技能仓库。集中管理自制 skill 和外部 skill 的登记，支持多机器同步。

## 目录结构

```
agent-skills/
├── catalog.yaml           # 【提交】技能总目录（homemade + external），跨机器共享
├── local.yaml             # 【gitignore】本机选择：从 catalog 里挑要启用的；每台机器不同
├── local.yaml.example     # local.yaml 的样例，提交到 git
├── install.sh             # 安装/同步脚本（按 local.yaml 把 skill 装到本机）
├── skills/                # 自制 skill 源
│   └── feishu-claude-bridge/
│       └── SKILL.md
└── docs/
    └── install-design.md  # install.sh 的设计文档
```

### catalog.yaml vs local.yaml
| 文件 | 是否提交 | 作用 |
|---|---|---|
| `catalog.yaml` | 提交 | 全量清单：有哪些 skill 可用、来源、描述。所有机器共享。 |
| `local.yaml` | gitignore | 本机选择：从 catalog 里挑要启用的（`selected`），外加本机手动装、未进 catalog 的（`machine_local`）。 |

## 两条不变量
1. **特性 1**：`catalog.yaml` 是唯一的事实来源 —— 一个 skill 要么在 homemade（本仓库源），要么在 external（外部来源），不登记就是不存在的。
2. **特性 2**：`local.yaml` 只做"选择"，不发明新条目 —— `selected` 必须能在 `catalog.yaml` 里找到；`machine_local` 是本机手动装的、显式标注"未进 catalog"。

## 运行 install.sh
```bash
cd ~/agent-skills
./install.sh
```
首次运行（无 `local.yaml`）会扫描 catalog 并交互式让你选；之后按 `local.yaml` 同步。

> install.sh 的完整逻辑尚在设计中，当前仓库里是骨架。设计见 [`docs/install-design.md`](docs/install-design.md)。

## 新增自制 skill
1. 在 `skills/<skill-name>/` 下写 `SKILL.md`（YAML frontmatter: `name`, `description`）。
2. 在 `catalog.yaml` 的 `homemade` 列表加一条：`name` / `path` / `desc`。
3. 把 skill 名加进本机 `local.yaml` 的 `selected`（复制 `local.yaml.example` 改）。
4. 运行 `./install.sh`。

## 登记外部 skill
在 `catalog.yaml` 的 `external` 列表加一条：
```yaml
external:
  - name: <skill-name>
    kind: plugin        # plugin | marketplace | git
    source: <url 或 marketplace 名>
    install_hint: <可选，给人看的安装提示>
```
然后加进 `local.yaml` 的 `selected`。
