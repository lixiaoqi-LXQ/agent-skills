---
name: feishu-claude-bridge
description: >
  当用户想从飞书（手机/任意端）远程驱动服务器上的 Claude Code，或想让 CC 在服务器跑、
  遇到需要确认/讨论时通过飞书卡片推送并接收回复时使用。也适用于"把飞书消息当作 CC 的 stdin、
  CC 的输出流式回飞书"这类远控/通知闭环场景。涉及的工具是 lark-channel-bridge（npm 包，
  GitHub: zarazhangrui/lark-coding-agent-bridge）。
---

# 飞书远控 Claude Code（lark-channel-bridge）

把飞书消息桥接到本机的 `claude` CLI，再把 Claude Code 的输出以**流式卡片**渲染回飞书。
每会话/话题/文档评论独立 session，支持多 workspace、`/cd` 切目录。底层用飞书官方
`@larksuite/channel` 长连接 SDK，**WebSocket 主动出网**，不需要公网 IP 或回调地址
—— 对内网部署很关键。

## 工作原理（high-level）

bridge 是飞书聊天 ↔ 本地 `claude` 终端之间的**双向翻译管道**，自己不跑模型：
- **飞书侧**：拿你的自建应用凭证，以 bot 身份 WebSocket 主动连飞书，收消息事件、发流式卡片。
- **本地侧**：把 `claude` CLI 作为子进程拉起（streaming JSON），飞书消息 → 写进 claude stdin；
  claude 流式输出 → 渲染成飞书卡片。真正的 Claude 用你本地 claude 的登录鉴权调 API。

**基数关系（重要）**：
- **bot ↔ bridge 进程 = 1:1**。一套 app 凭证 = 一个 profile = 一个 bridge 进程。要多 bot →
  多 profile（`profile create` + 各自 app），分别 `start --profile X`。
- **1 bot ↔ claude session = 1:多**。一个 bot 下可有多个 session，按**飞书会话维度**（chatId）
  自动隔离：每个私聊 / 群 / 群内话题 / 文档评论线程 = 独立 session，上下文互不干扰。

## 适用场景
- **远控**：手机或任意端，从飞书驱动服务器上的 Claude Code。
- **通知/确认闭环**：CC 在服务器跑、需要确认或讨论时，通过飞书卡片推送；用户在飞书
  直接回复即可继续（飞书消息 = CC 的 stdin）。
- **能力边界（重要）**：CC 在 streaming 模式下没有"危险命令停下等审批"的中间态，权限靠
  permission mode 静默控制（`full` = bypassPermissions 全自动 / `workspace` = acceptEdits /
  `read-only` = plan 只规划等确认）。所以"危险操作要审批"只能靠收紧到 plan 模式近似实现。

## 前置条件
- Node ≥ 20.12（实测 v24 OK）
- 本机 `claude` CLI 已装且已登录
- 飞书企业管理员权限（能建自建应用 + 审批权限范围）

## 步骤 1：装 bridge
```bash
npm i -g lark-channel-bridge
lark-channel-bridge --version   # 验证，实测 0.5.4
```
nvm 用户直接全局装无权限问题；非 nvm 遇 EACCES 用 `npm config set prefix ~/.npm-global`
+ 加 PATH，**不要 sudo**。

## 步骤 2：建飞书自建应用（open.feishu.cn）
1. 创建企业自建应用，拿 App ID（`cli_xxx`）+ App Secret。
2. 应用能力 → 添加「机器人」。
3. 「事件与回调」→ 打开「**长连接模式**」（关键！不填请求地址）。
4. 事件订阅：订阅「接收消息 v2.0」(`im.message.receive_v1`)。
5. **权限范围**（实测必须的清单，发布版本 → 管理员审批）：
   - `cardkit:card:write` —— 流式卡片回复，**实测必加，否则发不出回复（报 99991672）**。
   - `application:application:self_manage` —— 让 bridge 自动识别应用 owner，**实测必加，
     否则所有人都被判 denied-user 静默忽略**。
   - `im:message:send_as_bot`、`im:message`、`im:message.group_msg` —— 收发消息。
   - `im:resource`（图片/文件）、`im:chat`（会话信息）、`contact:user.id:readonly`（用户身份解析）。
6. 发布版本 → 审批通过 → 可用范围设「全员可用」或加自己。
7. 在飞书搜到 bot，私聊发一句话建立会话。

## 步骤 3：绑定（服务器终端，首次交互式一次）
```bash
lark-channel-bridge run --app-id cli_xxxxxxxxxxxx
# 提示输 App Secret → 选 agent=claude → 选工作目录（之后可 /cd 改）
```
飞书中国版默认 `--tenant feishu` 不用加；Lark 国际版加 `--tenant lark`。
非交互可用 `--app-secret <secret>`。
**凭证只首次输入**：App ID 进 `config.json`、Secret 加密进 `profiles/<p>/secrets.enc`，
之后 `run` / `start` 直接复用，不再提示。

## 步骤 4：常驻（systemd 或 tmux 二选一）
前台 `run` 验证能收发后，两种续命方式：
```bash
# 方式 A：systemd 守护（崩了自动拉起、开机自启）
lark-channel-bridge start && lark-channel-bridge status

# 方式 B：tmux 前台（自己管，功能一样）
tmux new -s lark-bridge
lark-channel-bridge run --app-id cli_xxx     # 已绑定过则不用 --app-id
# Ctrl-b d 脱离；tmux attach -t lark-bridge 回来
```

## 常用 slash 命令（在飞书里发给 bot）
- `/cd <path>` 切工作目录；`/ws save|use|list|remove` 管理 workspace。
- `/new` `/reset` 清 session；`/resume` 恢复历史。
- `/config` 调回复模式（流式卡片 vs 纯文本）、permission mode、是否群内需 @。
- `/invite user|admin|group @人` 放权（默认只有 owner 能用）。
- `/status` `/doctor` 排障。
- 群里需 `@bot`，私聊不用。

## 多 session / 多群并发（1 bot 对多 session）

**典型诉求**：1 个 bot + 1 个 bridge 进程，对接多个 claude session，各群独立汇报、并行执行。
这是原生支持的——不同飞书群（chatId）= 不同 session，天然隔离。

**落地步骤**：把 bot 拉进多个群，每个群第一次绑定一次：
```
# 在群 A 里：
/cd /path/to/project-A     # 切到该 session 所属的项目目录（session 按目录存）
/resume                    # 列出该目录的历史 session（含终端开的），挑一个；或 /new 新开
# 在群 B 里：
/cd /path/to/project-B
/resume                    # 绑另一个 session
```
要点：
- `/resume` 列的是**当前 `/cd` 目录下**的 claude session（读 `~/.claude/projects/<cwd>/`），
  所以先 `/cd` 到目标项目，再 `/resume` 才能看到对应 session。
- **绑定一次即持久**：绑完群↔sessionId 写进 `sessions.json`，之后该群消息自动续这个 session，
  无需每次 resume。换 session 再 `/resume` 或 `/new`。
- **真并发**：不同群的 session 由 ProcessPool 并行 spawn 多个 claude 子进程，默认
  `maxConcurrentRuns=10`（上限 50）。各群 bot 独立流式卡片汇报，互不阻塞。
  调并发：`/config` 或编辑 `preferences.maxConcurrentRuns`（1~50）。
- **同 chat 内不能并行**：同一群/私聊只有一个 session、消息排队一轮一轮；要在同一处并行
  只能拆成多个群 / 多个话题线程 / 多个文档评论线程。
- 实际瓶颈：本机资源（每个 claude 子进程）+ Anthropic API 速率限制，并发数别一味拉满。

## permission mode 与"确认/通知"需求的映射
- **讨论 / CC 提问**：天然闭环（CC 卡片输出问题 → 你回复 → 继续）。
- **危险操作审批**：收紧到 `workspace` 或 `plan`（`/config` 改）；plan 模式下 CC 只规划、
  等你在飞书确认才执行。

## 排障（两个实测踩坑）
1. **报 `denied-user` / 不回消息**：bridge 启动时查 owner 失败（缺
   `application:application:self_manage`）。临时绕法：把你的 open_id 写进
   `~/.lark-channel/config.json` 的 `profiles.<name>.access.allowedUsers` 和 `admins`
   （open_id 可从 `~/.lark-channel/profiles/<name>/logs/bridge-*.jsonl` 的 `sender`
   字段 grep 到），重启 bridge。治本还是加权限。
2. **报 `99991672 cardkit:card:write`**：流式卡片权限缺失。去开放平台加
   `cardkit:card:write` → 重新发版审批 → 重启。

日志位置：`~/.lark-channel/profiles/<profile>/logs/bridge-YYYYMMDD.jsonl`，
用 `grep 'event":"fail\|skip-not-allowed\|owner_refresh_failed'` 快速定位。

## 安全
- 默认仅 owner 可用，扩展用 `/invite`。
- 权限模式默认 `full`（全自动），生产建议收紧到 `workspace` 或 `plan`。
- App Secret 别进 git/对话，用交互输入或 secret 管理。
