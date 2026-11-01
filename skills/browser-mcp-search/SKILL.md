---
name: browser-mcp-search
description: 使用 playwright MCP 在已登录浏览器中搜索/浏览/交互任意网站（小红书、抖音等社交平台站内搜索、读正文评论、发消息）。当任务需要复用浏览器登录态或站内操作时使用。
---

# 浏览器自动化

20+ 个 `browser_*` 工具按任务自由组合。站点特定知识（URL、选择器、交互习惯）见 `sites/` 子目录，现有：`xiaohongshu.md`。初始化见 `SETUP.md`；`scripts/probe.py` 仅诊断用。

**通道**（用户指定则从之）：

| 通道 | 浏览器 | 适用 |
|---|---|---|
| `playwright-edge` | Windows 已登录 Edge | **默认**。复用全部登录、指纹拟真；接管前台焦点；多客户端天然隔离（各占一个标签组，组名 `Playwright · <client名>`，client 名可用 `PW_MCP_CLIENT_NAME` 自定义） |
| `playwright-bg` | WSL headless Chromium | 用户在忙、不能被打扰时。多 agent 并行需各自设 `PW_MCP_PROFILE=<名>`（登录态独立） |

拿不准要哪个通道时，直接问用户。

## 核心范式（顺序即优先级）

1. **快照 + ref 交互**：`browser_snapshot` 拿语义树（含 `ref=xxx`）→ 按 ref `browser_click` / `browser_type`。不要猜 CSS 选择器
2. **可信点击**：`browser_click`（CDP 真实输入事件）。`dispatchEvent` 合成的 click/hover 会被 React 组件忽略
3. **URL 直达**：UI 点击打不开时，读快照中链接的 `/url` 字段拿真实路径直接 `browser_navigate`
4. **数据提取**：`browser_evaluate` 返回结构化 JSON（切片限量）；评论等懒加载内容需先滚动
5. **每步验证**：关键操作后 snapshot 确认（如发出的消息出现在正文区）

## evaluate 传参规范

JS 参数经多层转义（shell→JSON→管道）极易损坏。正确姿势：JS 写入临时文件 → `json.dumps` 序列化 → 单行发送。避免手写内联转义。

## 风控纪律（对任意站点）

- 关键词不重复；禁止秒级连发相同动作（无需主动 sleep，思考时间即间隔）
- 禁止用重开会话/新标签页的方式"重试"；每个 MCP 会话都是冷启动
- 每步检查登录墙/验证元素，出现即停
- 遇风控信号**渐进冷却**：停 5 分钟轻探（打开首页级的最轻动作）→ 仍异常按 10/15/20 分钟递增，封顶 30 分钟；到顶仍封则报告用户
- 验证码、扫码一律交用户人工处理
- 多 Agent 并行（edge 通道各占独立标签组）：不同站点可随意并行；同站 ≤2 个且关键词错开，绝不同时搜同一个词；任务结束后关闭本组标签（断开的会话标签会残留；凡 `Playwright ·` 前缀的组/标签均为 Agent 创建，可安全整组关闭）

## 边界

- 图片仅能取 URL，且须限定在内容容器内提取（页面级 `img` 扫描会混入推荐流/广告图）
- 登录态判断：HttpOnly cookie 读不到，用间接信号（特定可见 cookie + 无登录墙）
- 只做用户明确要求的操作；发消息等外发动作需用户明示
