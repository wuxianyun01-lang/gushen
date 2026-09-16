# 股神 · 投资顾问

个人股票/基金投资顾问系统。按需分析，给结论 + 未来走势预判；不实时盯盘、不自动交易。

## 功能

- 按需分析股票/ETF/场外基金（行情、技术面、消息面、情绪面）
- 预测引擎：技术模型 + 大师框架 + 舆情 + 趋势 + TradingAgents-CN 多智能体，五分量加权
- 30+ 投资大师视角（巴菲特、格雷厄姆、林奇等）
- 自进化：预测账本、错误教训、概率校准

## 换电脑恢复（一键）

1. 克隆本仓库
2. 右键 `install.ps1` → "使用 PowerShell 运行"（需联网，自动完成全部安装）
3. 编辑 `monitor/config.json`，填入持仓和 QQ 邮箱授权码
4. 在 Codex 里说"用股神顾问分析 XX"即可

`install.ps1` 会自动：
- 安装 30+ 投资大师 skill + 股神顾问 skill 到 `~/.codex/skills/`
- 克隆并安装 TradingAgents-CN（多智能体分析）
- 生成配置模板

## 目录

- `monitor/` 分析与预测代码
- `docs/` 交易体系与项目记忆
- `skills/` 备份的 Codex skills（大师 + 股神顾问）
- `AGENTS.md` 顾问工作规则

## 重要边界

- 不自动下单，不读取券商交易接口
- 不在公开文件保存 API Key、邮箱授权码
- 场外基金正式净值以基金公司晚间公布为准
- 所有历史案例和模型概率都不代表保证收益

## 第三方组件与许可

- 本仓库代码：MIT License
- TradingAgents-CN（多智能体分析）：[Apache License 2.0](https://github.com/hsliuping/TradingAgents-CN)，由 `install.ps1` 从官方仓库克隆，本项目仅调用其分析能力，不包含其源码副本。
- 投资大师 skill（`skills/master-*-perspective`）：整理自公开资料（股东信、著作、访谈）。
- 交易体系（`docs/交易体系.md`）：个人投资经验总结。
