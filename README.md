# PBRD v0.0.1（测试版）

通过本地网页描述板级需求，保存项目 JSON，再由模板生成板级源码和工程。项目需求由人审核，工具负责依赖检查、重复配置和工程装配。

## 开始使用

1. 将本仓库放在产品项目根目录下，目录名为 `pbrd`，与 `product` 同级。需要 Python 3.8 或以上版本；日常运行仅使用 Python 标准库，不需要安装 Node.js。
2. Windows 双击 `start-config.cmd`。脚本会刷新本项目的数据快照、打包网页并启动本地服务。浏览器未自动打开时，复制窗口中的 `http://127.0.0.1:端口/` 打开。CMD 窗口保持运行是正常现象，关闭窗口或 Ctrl+C 会停止服务。
3. 在“项目与平台”填写产品、版本号（如 R01V02）、目标和输出目录，选择 JSON 保存文件夹并填写文件名。不要使用原工程目录测试。
4. 选择模块，配置实例、器件、公共总线和引脚，核对 IO 使用总表及依赖提示。
5. “保存 JSON”只保存输入；“保存并构建工程”先保存 JSON，再生成代码和工程文件。这里的构建指工程生成，不会自动调用 Keil 编译。

菜单提供新建项目、导入 JSON、保存 JSON、保存并构建工程、本地同步。新建项目恢复默认配置；旧项目可通过导入 JSON 恢复。关闭网页的提示不能代替主动保存，浏览器不保证关闭时完成文件写入。

请使用本地服务网址。直接打开 `file:///.../board-config-preview.html` 仅适合离线预览，无法完成本地文件夹选择、同步和工程生成。

## 输入与输出

- 项目 JSON 保存位置及名称由页面设置；路径为空时禁止保存。建议每个实际产品将它与产品源码一起版本管理。
- 源码与工程输出位置由项目 JSON 的 `output.directory` 指定，通常为 `product/src/brd/r01v02`。输出包括 cfg、def、src、工程文件及项目专用 `check_list.md`。
- 扫描、差异和生成报告位于 `pbrd/.reports/`，不放进产品输出目录。
- 已管理目录重新生成会核对生成区并保留约定的用户代码区；随意修改生成区可能导致更新被拒绝。`.reports/generation/<输出目录名>/.pbrd-manifest.json` 是本机更新状态，不能当普通缓存删除。换机器后不要直接覆盖已有目录，先生成到新目录比较。
- `examples/HQT401_L30_R01V02.json` 是当前产品的示例，包含多个 ADC 和共用物理 IIC1 的 DA280B、LSM6DSL；导入后必须核对输出模式、目录、引脚和产品需求。

命令行生成：

```powershell
python -B generate.py --config examples/HQT401_L30_R01V02.json --output ../product/src/brd/你的测试目录
python -B scan-project.py
python -B ui/local_server.py --check
```

默认项目根目录由 `pbrd.config.json` 指向上一级，也可使用 `--project-root`。输出为已存在的目录时仍受创建/重新生成模式和保护规则约束。

## 同步与支持范围

`ui/source-settings.json` 记录版本枚举、板级功能枚举、各平台 BRD/DRV 目录及引脚资料位置。启动时刷新快照；页面“本地同步”可重新读取更新。扫描发现未知模块只会提示待接入，不会自动编写未经审核的模板。

v0.0.1 已联调 AC78428 + Keil 5.23 路径。此前示例 App/Boot 经本机 ARMCC 编译验证；这不代表任意配置都已验证，也未替代硬件测试。IAR、CMake 和其他 MCU 仍需要相应工程适配器、平台资料与验证，不能仅凭页面选项认为已经支持。已有源码反向解析也只覆盖已知项目风格，不是通用 C 解析器。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `ui/` | 网页源码、本地服务、来源扫描与导入 |
| `modules/` | 可选模块、器件、字段和依赖定义 |
| `platforms/` | MCU 引脚、已审核默认值与生成装配规则 |
| `templates/` | 正式代码和工程模板 |
| `generator/` | 参数映射、模板渲染、工程装配及写入保护 |
| `examples/` | 示例及旧格式兼容输入（不是模板来源） |
| `tests/` | 生成、交互和兼容性验证 |
| `docs/` | 设计、生成和扩展说明 |

网页包 `board-config-preview.html`、`ui/platform-data.js` 在启动时生成，不提交 Git。`configs/` 是本机用户保存数据；`old/` 和 `maintenance/` 是本地历史参考，不参与运行，也不提交。`.reports/`、`output/`、Python 缓存和测试截图同样忽略。仓库不包含产品 SDK、编译器和 IDE，请搭配产品项目使用。

进一步阅读：[设计思路](docs/ARCHITECTURE.md)、[生成与维护](docs/GENERATION.md)、[添加模块及平台](docs/ADDING_MODULES.md)、[测试说明](tests/README.md)、[版本记录](CHANGELOG.md)。
