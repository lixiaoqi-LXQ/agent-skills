---
name: browser-mcp-search
description: 使用 playwright-edge 浏览器 MCP 在已登录的 Windows Edge 中搜索小红书/抖音/通用网页，读取正文、发布时间、评论并保留原始链接。当任务需要在社交平台站内搜索或复用浏览器登录态时使用。
---

# 浏览器搜索（playwright-edge）

用名为 `playwright-edge` 的 MCP 服务（stdio）驱动本机**已登录的 Windows Edge**。Agent 拥有完整的浏览器探索权限：MCP 提供 20+ 个 `browser_*` 工具（点击、截图、填表、按键、快照、执行 JS……），按任务需要自由组合使用，不受本 skill 限制。

- 全新机器初始化：见本目录 `SETUP.md`
- `scripts/probe.py` **仅用于诊断**（MCP 层排障、无客户端环境下直测），正常使用一律走 MCP 工具

> 若本地注册的 MCP 服务名不是 `playwright-edge`，以 `claude mcp list`（或客户端等价命令）显示的名称为准。

## 标准流程（参考路径，非强制——按任务自由取舍或改用其他 browser_* 工具）

1. **新开标签页**（复用登录态，勿动用户已有标签页）：
   `browser_tabs {"action":"new","url":"<搜索URL>"}`
   - 小红书：`https://www.xiaohongshu.com/search_result?keyword=<URL编码关键词>`
   - 抖音：站内搜索或直接 `https://www.douyin.com/search/<关键词>`
   - 通用：任意搜索引擎 URL
2. **显式切换到新标签**（关键！evaluate 只作用于"当前"标签页）：
   `browser_tabs {"action":"select","index":<新标签的序号>}`
3. **提取搜索结果**：`browser_evaluate` 取标题+链接。小红书示例：
   ```js
   () => Array.from(document.querySelectorAll('a[href*="/search_result/"], a[href*="/explore/"]'))
     .filter(a => a.innerText.trim())
     .slice(0, 10)
     .map(a => ({ title: a.innerText.split('\n')[0].slice(0, 80), href: a.href }))
   ```
4. **打开结果**：`browser_navigate {"url":"<结果链接>"}`。
   小红书链接的 `xsec_token` 参数**必须原样保留**，否则打不开。
5. **读内容**：`browser_evaluate` 提取结构化字段。小红书笔记页选择器：
   - 标题 `#detail-title`；正文 `#detail-desc`；作者 `.username`；日期 `.date`
   - 评论 `document.querySelectorAll('.comment-item')`（每条 innerText）
   - 图片 URL：`#detail-title` 所在笔记容器内的 `img` 的 `src`
   - 永远返回 `location.href` 作为原始链接

## 连续搜索（已实测稳定）

多关键词连续搜索时**不要**每次新开会话/新标签页——那会重复冷启动并被风控识别（实测分钟级 10+ 次相同搜索即触发登录墙）。稳定做法（实测 3 连击无风控信号）：

1. 一个会话、一个标签页：首个关键词用 `browser_tabs {"action":"new"}`，之后一律 `browser_navigate` 在**同一标签页**换关键词（等效于人在搜索框改词）；
2. 每步间隔 ≥15 秒（阅读节奏）；
3. 关键词不同、避免完全相同的词反复搜；
4. 每次搜索后检查风控信号（`.login-container/.qrcode/[class*=login-modal]` 是否出现），一出现立即停止；
5. 触发过风控后冷却 30 分钟~半天自愈，通常无需重新登录。

## 注意事项

- 首次浏览器工具调用：Edge 弹出 connect 页后约 1 秒自动连上，无需用户操作；焦点短暂切到 Edge 属正常。
- 只做查询/读取；图片视频内容读不到（仅能取图片 URL），明确告知用户实际读取范围。
- 小红书 `web_session` 是 HttpOnly，`document.cookie` 看不到；判断登录态用 `unread` cookie 是否存在 + 无登录墙。
- 站点有频控，**必须克制**：连续操作之间停顿数秒；换关键词/翻页前等页面稳定。
- **每个新 MCP 会话都是一次冷启动**（新 connect 页 + 新标签页 + 重新加载），重复冷启动等同高频访问。一个任务尽量在单个会话内完成，不要用反复重开测试来"重试"。
- **出现登录二维码 / 风控验证页 = 立即停止一切重试**（越重试越严重），报告用户并建议冷却 10–30 分钟；冷却后仍要求扫码则说明登录态失效，由用户决定是否重新登录。切勿代替用户扫码或绕过验证。
- 会话结束后可提醒用户关闭带颜色的标签组。
- 仅当上下文确实加载不了 playwright-edge 的 MCP 工具、又必须完成浏览器任务时，才退回 `scripts/probe.py` 作临时传输层（`PROBE_TOOL_TIMEOUT` 控制每步间隔，默认 120 秒，建议 12–20）。
