# install.sh 设计文档

> 状态：**TODO / 待讨论**。install.sh 当前仅有骨架，完整逻辑待与用户确认后在此文档定稿，再回填实现。

## 待决问题
- 交互式选择用 `select`（POSIX 便携）还是 `whiptail`（更友好但需额外依赖）？
- homemade skill 的目标安装路径（不同机器 Claude Code skills 目录可能不同，需探测或可配置）。
- external 三种 kind（plugin / marketplace / git）的统一安装接口。
- 漂移检测的策略：每次运行都全量扫描，还是维护一份 installed 清单。
