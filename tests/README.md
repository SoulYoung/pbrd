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
