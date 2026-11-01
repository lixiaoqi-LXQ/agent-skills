# 小红书（xiaohongshu.com）站点地图

## 页面与 URL

| 入口 | URL |
|---|---|
| 搜索 | `https://www.xiaohongshu.com/search_result?keyword=<URL编码关键词>` |
| 笔记 | `https://www.xiaohongshu.com/explore/<id>`（**`xsec_token` 参数必须原样保留**，否则打不开） |
| 消息/私信 | `https://www.xiaohongshu.com/chat`（侧边栏"消息"是 popover，自动化下不可靠，直接走此 URL） |

## 搜索结果提取

- 结果链接：`a[href*="/search_result/"], a[href*="/explore/"]`，过滤 `innerText` 非空者
- 首行文本即标题；完整 `href` 含签名参数，后续导航直接用

## 笔记页选择器

- 标题 `#detail-title`；正文 `#detail-desc`；作者 `.username`；日期 `.date`
- 评论 `.comment-item`（**需先滚动评论区加载**：多次 `scrollBy` 后再提取）
- 原始链接一律返回 `location.href`

## 消息/私信交互（/chat 页）

- 左侧为会话列表（含单聊与群聊），点击进入
- 输入框：`.xhs-im-input-bar-editor`（contenteditable，placeholder「发消息...」），**回车即发送**，无独立发送按钮
- **输入必须用 `browser_type` + `slowly:true`**（逐字符真实键入）；`.fill()` 或普通 type 的值会被 React 抹掉，且不触发 input 事件
- 发送后用 snapshot 验证：消息需同时出现在聊天正文区和侧边栏该会话的预览里

### @ 提及成员

1. 点击输入框聚焦 → `browser_press_key {"key":"@"}` 唤起成员弹层
2. 弹层 class 为 `.xhs-im-mention-picker-list`（**不在 a11y 快照里**，需 evaluate 按 class 确认是否弹出）
3. 弹层项 `.xhs-im-mention-picker-item` 持续重渲染，`browser_click` 会因"等待稳定"超时——**用键盘选择**：`ArrowDown` 次数 = 目标序号 + 1（默认高亮第一项，选中第 2 项需按两次），然后 `Enter`
4. 选错可 `Backspace` 删除提及芯片后重来
5. 补充正文用 `slowly:true` 键入（勿用 fill，会清掉芯片），Enter 发送；真提及会渲染为芯片而非纯文本

## 登录态判断

- `web_session` 为 HttpOnly，`document.cookie` 读不到
- 间接信号：存在 `unread` cookie + 页面无登录弹窗（`.login-container / .qrcode / [class*=login-modal]`）

## 已知限制

- 笔记图片懒加载且推荐流/广告图与正文图同 CDN 同尺寸，直接扫 `img` 会混入无关图；须限定在笔记媒体容器内（结构随版本变化，使用前现场用 snapshot 确认）
- 未登录或高频访问会触发风控（登录墙/滑块），处理原则见主 skill 风控纪律
- 网页版功能少于 App（如部分互动无入口）
