---
name: browser-mcp-search
description: 使用 playwright-edge 浏览器 MCP 在已登录的 Windows Edge 中搜索小红书/抖音/通用网页，读取正文、发布时间、评论并保留原始链接。当任务需要在社交平台站内搜索或复用浏览器登录态时使用。
---

# 浏览器搜索（playwright-edge）

用名为 `playwright-edge` 的 MCP 服务（stdio）驱动本机**已登录的 Windows Edge**。本 skill 的所有文档与脚本都在自身目录内，不依赖特定机器路径。

- 全新机器初始化：见本目录 `SETUP.md`
- 脱离客户端直测：`python3 <skill目录>/scripts/probe.py browser_tabs '{"action":"list"}'`

> 若本地注册的 MCP 服务名不是 `playwright-edge`，以 `claude mcp list`（或客户端等价命令）显示的名称为准。

## 标准流程

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

## 注意事项

- 首次浏览器工具调用：Edge 弹出 connect 页后约 1 秒自动连上，无需用户操作；焦点短暂切到 Edge 属正常。
- 只做查询/读取；图片视频内容读不到（仅能取图片 URL），明确告知用户实际读取范围。
- 小红书 `web_session` 是 HttpOnly，`document.cookie` 看不到；判断登录态用 `unread` cookie 是否存在 + 无登录墙。
- 站点有频控：连续操作之间稍作停顿；触发验证码时请用户人工处理后继续。
- 会话结束后可提醒用户关闭带颜色的标签组。
- 若上下文中没有加载 playwright-edge 的 MCP 工具，用 `scripts/probe.py` 作为传输层（`PROBE_TOOL_TIMEOUT` 控制每步间隔，默认 120 秒，调试建议 12）。
