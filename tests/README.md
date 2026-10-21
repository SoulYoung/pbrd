# 验证说明

日常使用不需要测试依赖。下面命令从 pbrd 目录执行，使用配套产品源码；部分用例基于当前 HQT401_L30 示例，不是跨产品通用测试。

```powershell
python -B ui/local_server.py --check
python -B ui/build_catalog.py
python -B ui/build_preview.py
python -B tests/verify_generation.py
```

浏览器测试需要 Node.js 和 Playwright（见 package.json），运行 `npm test --prefix tests`。浏览器和 Python 测试会产生 `.reports/` 等本地文件，部分生成测试会临时创建板级目录并在结束时清理。

`verify_references.py` 需要当前示例 r01v02 已生成，用来核对命名、注释、实例及参考目录未改变。它的可选 `--compile` 分支以及部分预处理/编译测试仍有本机工具链路径，需要先按测试脚本参数或本机环境调整；不能视为通用 CI。

发布前至少确认从干净源码可启动、来源读取成功、JSON 导入导出正常、模板生成用例通过。编译验证需另行提供合法可用的嵌入式工具链。不要把运行服务的日志或实时生成状态作为可随意删除的缓存。

引脚候选控件的无浏览器校验：`node tests/verify_pin_choices.cjs`。覆盖可填写下拉列表、大小写归一化、候选范围、空值及保存拦截；真实页面交互仍需运行浏览器测试。

输出目录回归：`python -B tests/verify_output_paths.py`，覆盖 r01v01、自定义嵌套路径、Keil 引用以及创建/重新生成保护，不执行编译。


当前 TXJ_BR4_CX20P 配置的生成质量检查：

- `python -B tests/verify_power_callbacks.py`：公共电源回调命名、复用及排序稳定性。
- `python -B tests/verify_codegen_quality.py`：CAN 电源/FD、计数、RTC/IC 卡宏及 Flash 行为。
- `python -B tests/audit_all_configurations.py`：原 r01v02 与 `.reports/code-review-20261020` 全部配置对象图对比，已确认的 Sw4/新增 KeyCall/未选中 Boot XCU SPI 单独记录。
- `python -B tests/verify_all_generated_units.py`：以真实 Keil 工程头文件路径编译审阅目录的全部生成板级源文件，不执行 SDK 发布；需要本机 ARMCC。


## 产品专项验证的输入

`verify_codegen_quality.py`、`verify_imported_modules.py`、`verify_power_callbacks.py`、`verify_xcu.py` 等用例读取本机 `configs/TXJ_BR4_CX20P_R01V01.json`。该目录按工具仓库规则忽略，需要从对应产品取得配置；这些脚本不能当作干净克隆后全部可运行的通用 CI。

`audit_all_configurations.py` 还依赖原 r01v02 和审阅输出，其差异白名单对应当时的审阅快照。后续启用 Boot XCU SPI 等变化后，应更新比较输入和审阅结论，不能直接把旧白名单结论套在新配置上。

`node tests/verify_capture_mux_ui.cjs` 验证芯片引脚派生的计量实例/通道下拉、数字类型和 XCU SPI 复用提示；`node tests/verify_xcu_hints.cjs` 验证模式与 REQ 参数提示。两者使用仓库平台/模块资料，不需要当前产品 configs。

`verify_all_generated_units.py <板级输出目录>` 可指定实际输出目录，依赖生成的 Keil 工程、配套产品 SDK 与本机 ARMCC；默认审阅目录并不随仓库上传。
