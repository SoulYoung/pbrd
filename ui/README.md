# 前端与本地服务

用户操作见上一级 README。推荐从 `start-config.cmd` 运行，服务仅监听 127.0.0.1。

- `local_server.py`：来源同步、文件夹选择、JSON 保存和显式工程生成接口。
- `app.js`、`style.css`：配置交互和样式。
- `frontend-model.js`：默认状态、JSON 迁移及通用配置模型。
- `data-loader.js`：本地数据接口与离线快照加载。
- `frontend-fields.json`：复杂模块字段覆盖。
- `source-settings.json`：各平台数据来源，可随新平台追加。
- `build_catalog.py`：根据真实项目生成 platform-data.js。
- `build_preview.py`：把前端源码打包为 board-config-preview.html。

服务每次启动自动执行两个打包步骤；开发时也可单独执行 `python -B ui/build_catalog.py` 和 `python -B ui/build_preview.py`。两个生成文件由 Git 忽略。

普通模块优先通过 modules/*.json 接入；复杂字段、器件选择和生成语义的修改需要同步检查字段覆盖与生成器，参见 docs/ADDING_MODULES.md。
