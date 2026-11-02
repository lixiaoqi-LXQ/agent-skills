---
name: plannotator-feedback
description: 在 VS Code 内使用 Plannotator 让用户批注文档、目录或代码更改；等待用户提交反馈，修改原文件后自动重新打开复审。用于用户要求人工 review、批注或送审的场景。
---

# Plannotator Feedback

让当前 agent 把用户指定的内容送入 VS Code 的 Plannotator，等待批注、修改并再次送审。一次临时会话指一个 Plannotator 实例，不是新建 AI 对话。只收集反馈；不创建分支、提交、快照或版本管理系统。

## 启动

以下 `SKILL_DIR` 指本技能目录，执行时替换为真实路径。先运行：

```sh
python3 SKILL_DIR/scripts/review.py doctor
```

缺少 CLI 或扩展时，才读取 [安装说明](references/installation.md)，自动补齐依赖。现有依赖直接复用；不每次升级。自动安装是此流程的一部分，无需再次询问。

选择目标与模式：

```sh
# 单个文档或目录：渲染文档，目录可切换文件
python3 SKILL_DIR/scripts/review.py document /absolute/path/to/doc-or-folder --workspace /absolute/vscode/workspace

# 仓库当前未提交更改
python3 SKILL_DIR/scripts/review.py changes /absolute/repo --diff-type uncommitted --workspace /absolute/vscode/workspace

# 指定比较范围
python3 SKILL_DIR/scripts/review.py changes /absolute/repo --base main --diff-type since-base --workspace /absolute/vscode/workspace

# 已有精确补丁，可用于“本轮任务的修改”
python3 SKILL_DIR/scripts/review.py changes /absolute/repo --patch-file /absolute/change.patch --workspace /absolute/vscode/workspace
```

- `--workspace` 指用户实际正在看的 VS Code 窗口，目标文件可以位于该窗口根目录之外。优先复用调用终端的路由或已知当前工作区；不要机械地另开一个用户找不到的窗口。省略时脚本使用终端路由或目标目录的最长工作区匹配。
- 没有对应窗口时，脚本用 `code --new-window` 打开选定工作区，等扩展就绪。只走官方扩展 IPC；任何失败都不回退外部浏览器。
- “最近更改”按用户给出的范围执行。若能准确定位当前任务的修改，使用已有比较基线或精确补丁；没有依据时说明实际范围，默认显示全部未提交更改，不能声称那就是当前 agent 的修改。未跟踪文件不能假定都在 diff 中，必要时单独送审文档。脚本不自动建立版本基线。
- `--patch-file` 是静态差异；改完后由 agent 更新补丁再送审，不能把旧补丁原样重开。

脚本打印 `ready` 时包含独立 `session_dir`、目标和 VS Code 工作区。向用户说明已打开的文件和窗口，首次使用提示“选中文字 → Comment → Send Feedback”。使用适用的用户通知能力提醒一次。

## 等待、修改、复审

1. **保持当前 agent 回合等待。** 启动命令一直等待到提交或关闭。如果执行工具返回运行中的句柄，持续等待同一个句柄；不要结束回合、另开重复会话或只把 URL 发给用户。等待时仍要响应用户的消息与取消请求。
2. 最终输出含 `status: completed` 和 `result`。文档反馈通常在 `result.feedback`，更改审阅反馈在 `result.message`；用 `result.decision` 判断结果。
3. `annotated`：处理这次反馈中所有文件的实际修改请求。先读取当前源文件，保留用户已保存的编辑；不把已应用的 diff 再应用一次。Looks good 只表示认可，不要求修改。注释里的问题要直接回答或核实，不能把所有评论都当替换命令。
4. 修改或答复完成后，执行 `ack SESSION_DIR`，标记该轮已处理。**有实际修改时自动重开同一目标与范围供复审**，创建新的临时会话并继续等待。若本轮只有认可或没有待修改事项，可结束，不制造无限空复审。
5. `approved`：保留附带说明，结束本轮；不是自动提交、合并或执行实现计划的授权。`dismissed` 或用户明确说完成：结束，不再重开；关闭不是批准。
6. 用户要求停止等待时执行 `cancel SESSION_DIR`，只停止本会话。启动失败、服务异常或工具中断后，先查看该目录的 `server.log`、`status`，不要直接新建会话。向用户说明需其介入的阻塞，并发送适用通知。

恢复与状态命令：

```sh
python3 SKILL_DIR/scripts/review.py status SESSION_DIR
python3 SKILL_DIR/scripts/review.py wait SESSION_DIR --seconds 30
python3 SKILL_DIR/scripts/review.py reopen SESSION_DIR --workspace /absolute/vscode/workspace
python3 SKILL_DIR/scripts/review.py ack SESSION_DIR
python3 SKILL_DIR/scripts/review.py cancel SESSION_DIR
```

`wait` 返回 `waiting` 表示还没提交，继续等；超时不是批准、取消或用户完成。`reopen` 只重开同一存活会话的编辑器面板，不启动新的审阅服务。中断后的 AI 回合不会因为用户点 Send 自动恢复；用户恢复对话时用已记录的路径接回反馈。

## 会话隔离

每次用 `mkdtemp` 创建私有临时目录（Linux/WSL 通常为 `/tmp/plannotator-review-*`）。其中有 `session.json`、`feedback.json`、`server.log`、`data/`；`PLANNOTATOR_DATA_DIR` 单独设置，服务使用独立端口。目录只保留本次 Plannotator 状态，不承担项目版本组织。

- 当前 agent 保存自己命令返回的目录和执行句柄，只读取、确认或取消自己这一轮；不扫描 `/tmp` 找“最新反馈”，不按 `Codex` 等工具名共用文件。
- 不同 agent 可同时等待、接收各自反馈。VS Code 的全局 IPC 注册表只用于打开面板，不是反馈邮箱。
- **并行会话使用各自审阅页里的批注。** 当前官方扩展的源码编辑器快捷键使用全局 `activeProxyPort`，会路由到最后打开的会话；不能用它保证并行反馈隔离。
- `ack` 保留结果并记录处理时间；异常也保留文件供恢复。临时目录可能被系统清理，不作为长期档案。无需引入文件锁或多人修改同一文件的协调系统。
