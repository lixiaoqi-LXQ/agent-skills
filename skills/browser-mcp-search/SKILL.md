---
name: browser-mcp-search
description: 使用 playwright MCP 在已登录浏览器中搜索小红书/抖音/通用网页，读取正文、发布时间、评论并保留原始链接。当任务需要在社交平台站内搜索或复用浏览器登录态时使用。
---

# 浏览器搜索

20+ 个 `browser_*` 工具自由组合，不受本 skill 限制。初始化见 `SETUP.md`；`scripts/probe.py` 仅诊断用。

**通道**（用户指定则从之，未指定用默认）：

| 通道 | 浏览器 | 特点 |
|---|---|---|
| `playwright-edge` | Windows 已登录 Edge | **默认**；复用全部登录、指纹拟真；接管前台焦点；天然支持多客户端（每客户端独立标签组） |
| `playwright-bg` | WSL headless Chromium | 零干扰（备用）；多 agent 需 `PW_MCP_PROFILE=<名>` 各配独立 profile（登录态独立） |

用户在忙、不能被打扰时才用 bg；拿不准就直接问用户要哪个通道。

## 标准流程（参考，非强制）

1. `browser_tabs {"action":"new","url":"<搜索URL>"}` 新开标签页
   - 小红书：`https://www.xiaohongshu.com/search_result?keyword=<URL编码关键词>`
   - 抖音：`https://www.douyin.com/search/<关键词>`
2. `browser_tabs {"action":"select","index":<N>}` 切到新标签（evaluate 只作用于当前标签）
3. `browser_evaluate` 提取结果：`a[href*="/search_result/"], a[href*="/explore/"]` 的标题与 href
4. `browser_navigate` 打开结果（小红书链接的 `xsec_token` 必须原样保留）
5. `browser_evaluate` 读内容：`#detail-title` / `#detail-desc` / `.username` / `.date` / `.comment-item`（评论区需先滚动加载）；返回 `location.href` 作原始链接

## 连续搜索（实测稳定）

- 首个关键词用 tabs new，之后**同标签页** `browser_navigate` 换词；关键词不重复
- **无需主动 sleep**：Agent 的思考时间天然就是间隔。唯一禁止的是秒级连发相同动作
- 每步检查 `.login-container,.qrcode,[class*=login-modal]`，出现即停
- 每个 MCP 会话都是冷启动；禁止用重开 会话/标签页 来"重试"
- 触发风控后**渐进式冷却重探**：停 5 分钟 → 轻探一次（如打开首页）→ 仍异常则 10、15、20 分钟递增，封顶 30 分钟；到顶仍封则报告用户（可能需半天级或人工处理）。探测只用最轻动作，切勿反复触发

## 注意

- 图片仅能取 URL（直接 `img` 扫描会混入推荐流/广告图，需限定容器，未验证可靠选择器前明示局限）
- `web_session` 为 HttpOnly；判断登录态用 `unread` cookie + 无登录墙
- 只做查询/读取；频控敏感，遇验证码让用户人工处理
