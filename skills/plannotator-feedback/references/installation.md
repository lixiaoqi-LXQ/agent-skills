# 按需安装

只有 `review.py doctor` 显示依赖缺失时读取此文件。Linux、WSL 已验证；macOS 路径尚未实机验证。需 Python 3、VS Code CLI `code`（或设置 `PLANNOTATOR_CODE_CLI`）。不在被审阅项目中安装包或修改项目配置。

运行本技能的安装助手：

```sh
python3 SKILL_DIR/scripts/install.py
```

它只补齐缺失依赖：

- 从官方 `https://plannotator.ai/install.sh` 下载脚本到临时目录，用 `--minimal --non-interactive` 安装 CLI 到 `~/.local/bin`。官方安装器核对下载校验和。
- 使用当前环境的 `code --install-extension backnotprop.plannotator-webview` 安装扩展。在 WSL 中须使用连接当前 WSL 的 VS Code remote CLI，使扩展运行在正确宿主中。
- 不安装代理 hooks、额外 skills、Node 运行时或其他模型工具；不改写已有 AGENTS.md。

安装后再运行 `doctor`。扩展会登记 `~/.plannotator/vscode-ipc.json` 中的工作区端口。如果用户通过 `PLANNOTATOR_DATA_DIR` 或 XDG 修改了共享数据目录，助手也会按相同顺序寻找注册表；可用 `PLANNOTATOR_VSCODE_REGISTRY` 明确指定。

首次安装后可能需要新建 VS Code 集成终端；本技能通过 IPC 直接路由，不要求重启 agent。若扩展未激活，先打开正确工作区，必要时让用户执行 `Developer: Reload Window`，说明原因并通知用户。不得自行关闭用户窗口或启动外部浏览器。

若找不到 `code`，定位现有 VS Code 的命令行入口。若机器上没有 VS Code，需要用户完成 GUI 应用安装；不要把浏览器模式当替代结果。原生 Windows 尚未验证此 Python 助手，优先在已连接 VS Code 的 WSL 环境运行。

官方资料：

- https://docs.plannotator.ai/open-source/agents/vscode
- https://docs.plannotator.ai/open-source/start/installation

CLI 必须支持 `annotate --json` 和 `review --json`；当前验证版本为 CLI 0.28.44、扩展 0.16.8。版本更新后保留同样的端到端反馈测试，而非只检查命令能启动。
