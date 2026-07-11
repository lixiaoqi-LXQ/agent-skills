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

## 步骤 3：绑定（服务器终端，交互式）
```bash
lark-channel-bridge run --app-id cli_xxxxxxxxxxxx
# 提示输 App Secret → 选 agent=claude → 选工作目录（之后可 /cd 改）
```
飞书中国版默认 `--tenant feishu` 不用加；Lark 国际版加 `--tenant lark`。
非交互可用 `--app-secret <secret>`。

## 步骤 4：守护进程
前台 `run` 验证能收发后，Ctrl-C 停掉，挂 systemd：
```bash
lark-channel-bridge start    # 注册 systemd 用户单元
lark-channel-bridge status
```

## 常用 slash 命令（在飞书里发给 bot）
- `/cd <path>` 切工作目录；`/ws save|use|list|remove` 管理 workspace。
- `/new` `/reset` 清 session；`/resume` 恢复历史。
- `/config` 调回复模式（流式卡片 vs 纯文本）、permission mode、是否群内需 @。
- `/invite user|admin|group @人` 放权（默认只有 owner 能用）。
- `/status` `/doctor` 排障。
- 群里需 `@bot`，私聊不用。

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
