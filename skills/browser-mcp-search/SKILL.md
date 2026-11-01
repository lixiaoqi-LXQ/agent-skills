---
name: browser-mcp-search
description: 使用 playwright MCP 在已登录浏览器中搜索小红书/抖音/通用网页，读取正文、发布时间、评论并保留原始链接。当任务需要在社交平台站内搜索或复用浏览器登录态时使用。
---

# 浏览器搜索

20+ 个 `browser_*` 工具按任务自由组合。初始化见 `SETUP.md`；`scripts/probe.py` 仅诊断用。

**通道**（用户指定则从之）：

| 通道 | 浏览器 | 适用 |
|---|---|---|
| `playwright-edge` | Windows 已登录 Edge | **默认**。复用全部登录、指纹拟真；接管前台焦点；多客户端天然隔离（各占一个标签组，组名 `Playwright · <client名>`，client 名可用 `PW_MCP_CLIENT_NAME` 自定义） |
| `playwright-bg` | WSL headless Chromium | 用户在忙、不能被打扰时。多 agent 并行需各自设 `PW_MCP_PROFILE=<名>`（登录态独立） |

拿不准要哪个通道时，直接问用户。

## 搜索流程

1. `browser_tabs {"action":"new","url":"<搜索URL>"}` 新开标签页
   - 小红书：`https://www.xiaohongshu.com/search_result?keyword=<URL编码关键词>`
   - 抖音：`https://www.douyin.com/search/<关键词>`
2. `browser_tabs {"action":"select","index":<N>}` 切到新标签（evaluate 只作用于当前标签）
3. `browser_evaluate` 提取结果：`a[href*="/search_result/"], a[href*="/explore/"]` 的标题与 href
4. `browser_navigate` 打开结果（小红书链接的 `xsec_token` 参数必须原样保留，否则打不开）；后续换关键词也在**同一标签页** navigate，勿再开新页
5. `browser_evaluate` 读内容：`#detail-title` / `#detail-desc` / `.username` / `.date` / `.comment-item`（评论需先滚动加载）；返回 `location.href` 作原始链接

## 风控纪律

- 关键词不重复；禁止秒级连发相同动作（无需主动 sleep，思考时间即间隔）
- 多 Agent 并行（edge 通道各占独立标签组）：不同站点可随意并行；同站 ≤2 个且关键词错开，绝不同时搜同一个词；任务结束后关闭本组标签（断开的会话标签会残留；凡 `Playwright ·` 前缀的组/标签均为 Agent 创建，可安全整组关闭）
- 禁止用重开会话/新标签页的方式"重试"
- 每步检查 `.login-container,.qrcode,[class*=login-modal]`，出现即停
- 遇风控信号**渐进冷却**：停 5 分钟轻探（打开首页级的最轻动作）→ 仍异常按 10/15/20 分钟递增，封顶 30 分钟；到顶仍封则报告用户
- 验证码、扫码一律交用户人工处理

## 边界

- 图片仅能取 URL，且须限定在笔记媒体容器内提取（页面级 `img` 扫描会混入推荐流/广告图）
- `web_session` 为 HttpOnly；判断登录态用 `unread` cookie 是否存在 + 无登录墙
- 只做查询/读取
