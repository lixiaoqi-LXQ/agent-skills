# 初始化：Windows Edge + WSL 的 playwright-edge MCP（全新系统）

目标：Agent 留在 WSL，复用 Windows 侧日常 Edge 的登录态浏览网页。适用于任何
「AI 客户端在 WSL、浏览器在 Windows」的机器；macOS/Linux 单系统可跳过跨系统步骤。

## 架构

```
WSL: MCP 客户端 ─stdio→ pw-mcp-edge 启动脚本 ─→ playwright-mcp --extension
                                                    └ CDP relay（127.0.0.1 随机端口）
Windows: Edge（日常使用、已登录）+ Playwright Extension ←─WebSocket（localhost 转发）
```

首次调用浏览器工具时，服务端自动拉起 Edge 打开扩展 connect 页，凭 token 自动回连，
无需任何点击。WSL2 的 localhost 转发使 Windows 扩展能连回 WSL 内的 relay。

## 步骤

### 1. WSL 侧安装

```bash
npm install -g @playwright/mcp      # 提供 playwright-mcp 二进制；node ≥ 18
which playwright-mcp                 # 记下绝对路径，供启动脚本使用
```

### 2. Windows 侧安装扩展

在 Edge 打开 Chrome Web Store 安装 **Playwright Extension**
（ID `mmlmfjhmonkocbjadbfplnigmagldckm`；Edge 首次会提示「允许来自其他应用商店的扩展」→ 允许）。
没有 Chrome 也可以只用 Edge；有 Chrome 同理装一份。

### 3. 部署启动脚本

创建 `~/.local/bin/pw-mcp-edge`（可执行），内容：

```bash
#!/usr/bin/env bash
# Playwright MCP 扩展模式：连接 Windows 已登录 Edge
set -euo pipefail
PW_MCP_BIN="${PW_MCP_BIN:-<playwright-mcp 绝对路径>}"
EDGE_EXE="${PW_MCP_EDGE_EXE:-/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe}"
[ -x "$PW_MCP_BIN" ] || { echo "缺少 $PW_MCP_BIN（npm i -g @playwright/mcp）" >&2; exit 1; }
[ -e "$EDGE_EXE" ]  || { echo "找不到浏览器：$EDGE_EXE" >&2; exit 1; }
[ "${PW_MCP_DEBUG:-0}" = "1" ] && export DEBUG="${DEBUG:+$DEBUG,}pw:mcp:relay"
if [ -f "$HOME/.config/pw-mcp-edge.env" ]; then
  set -a; . "$HOME/.config/pw-mcp-edge.env"; set +a   # 关键：必须导出给子进程
fi
exec "$PW_MCP_BIN" --extension --executable-path "$EDGE_EXE" "$@"
```

要点：
- `--executable-path` 指向 Windows 浏览器，WSL 通过 interop 直接启动它（已运行的实例会复用，登录态不丢）。
- Chrome 用户把 `EDGE_EXE` 换成 `/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`。
- env 文件 `set -a` 导出是踩过的坑：漏掉则 token 传不进子进程，connect 页会一直等待手动选择。

### 4. 配置 token（自动授权）

1. Edge 工具栏点 Playwright 扩展图标 → 状态页复制 `PLAYWRIGHT_MCP_EXTENSION_TOKEN`
2. 写入 `~/.config/pw-mcp-edge.env`（权限 600）：
   ```
   PLAYWRIGHT_MCP_EXTENSION_TOKEN=<token>
   ```
3. 需要交互 shell 也可见时，在 `~/.zshrc` 加同名 `export`。

### 5. 注册到客户端（通用三件套）

```json
{ "mcpServers": { "playwright-edge": { "command": "~/.local/bin/pw-mcp-edge", "args": [], "env": {} } } }
```

Claude Code：`claude mcp add --scope user playwright-edge -- ~/.local/bin/pw-mcp-edge`
Codex（config.toml）：`[mcp_servers.playwright-edge]` + `command = "<绝对路径>"`

### 6. 验证（逐层，勿只看 Connected）

```bash
claude mcp list                                   # 1. 服务与工具发现
python3 <skill目录>/scripts/probe.py browser_tabs '{"action":"list"}'   # 2. 自动连接+列出标签
```
然后在客户端里让 Agent 完成一次真实搜索（skill 正文「标准流程」），确认能取正文与评论。

## 故障排查（按层定位，勿盲目重装）

| 症状 | 层 | 解法 |
|---|---|---|
| mcp list 连接失败 | 依赖 | 手动跑启动脚本看报错；node/npm 路径 |
| connect 页弹但不自动连、显示等待选标签页 | token 未导出 | 检查启动脚本 `set -a`；`bash -c 'set -a; . ~/.config/pw-mcp-edge.env; env|grep TOKEN'` |
| connect 页显示 Invalid token | token 过期 | 扩展里刷新过 → 同步更新 env 文件 |
| relay 卡在 Waiting for extension connection | 扩展/网络 | Edge 扩展管理确认已启用；`wsl.exe --shutdown` 重开（localhost 转发偶发失效） |
| 页面读取异常 | 网站 | 频控/验证码，人工处理后继续 |

## 安全

token 等同整个浏览器的访问权（含所有登录态）：文件 600 权限、勿入库勿外传。
Agent 仅做查询/读取类浏览。
