"""提示词领域模块（006）：功能注册表 / 模板存取 / AI 辅助。

- `registry`：功能定义、变量渲染语义、组合与校验（纯函数，不依赖 FastAPI/DB）；
- `store`：有效模板的读取/保存/恢复（经 settings_service 的 app_setting KV）；
- `assist`：AI 辅助编写（辅助提示词构建与调用）。
"""
