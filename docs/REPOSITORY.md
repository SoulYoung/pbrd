# PBRD 仓库上传与本机文件说明

本文针对独立的 pbrd Git 仓库。产品生成代码位于上级 product 工程，应按产品仓库规则另行提交。

## 需要提交的内容

| 路径 | 原因 |
| --- | --- |
| `generator/`、`generate.py` | 生成引擎、适配、写入与工程装配源码 |
| `modules/` | 正式模块与字段、器件、依赖定义 |
| `platforms/` | 正式平台引脚、默认值及生成规则；不是临时扫描输出 |
| `templates/` | C、头文件、工程和脚本模板，包括本次新加的 App XCU 模板 |
| `ui/` 中源码和 JSON 设置 | 页面、本地服务、扫描、同步、表单和默认来源配置 |
| `examples/` | 已审核的可复用示例和历史格式兼容输入 |
| `tests/` 中脚本、README、package.json | 验证逻辑及测试依赖声明；不是测试运行产物 |
| `docs/`、README、CHANGELOG、VERSION | 使用与设计维护说明 |
| `AGENTS.md`、`.gitignore`、`.gitattributes` | 维护约定、忽略及换行规则 |
| `start-config.cmd`、`scan-project.py`、`pbrd.config.json` | 启动、扫描和默认项目定位 |

`ui/source-settings.json` 和 `pbrd.config.json` 应保留可复用的项目相对路径。若在本机通过页面改成个人绝对路径，提交前核对差异；不能直接忽略这两个文件，否则干净克隆会缺少默认设置。

## 不上传工具仓库的内容

| 路径或类型 | 处理 | 说明 |
| --- | --- | --- |
| `.reports/` | 已忽略 | 扫描、审阅、差异、编译结果、生成状态；本机生成状态应保留 |
| `configs/` | 已忽略 | 当前产品业务配置；需要共享时另放产品仓库，或人工整理成 examples |
| `board-config-preview.html` | 已忽略 | 启动时可重建的页面包 |
| `ui/platform-data.js` | 已忽略 | 启动时可重建的数据快照 |
| `output/`、`generated/` | 已忽略 | 本机生成目录，正式产品输出按产品仓库管理 |
| `old/`、`maintenance/` | 已忽略 | 本地历史参考，不参与正式运行 |
| Python 缓存、日志、node_modules、.venv、.env | 已忽略 | 缓存、安装依赖或本机环境 |
| `.o/.obj/.axf/.elf/.hex/.map/.crf/.d/.pdb` | 已忽略 | 编译输出；不影响 `.c.template` 等正式模板 |
| `.pbrd-*.tmp`、生成锁和 staging 残留 | 已忽略 | 异常残留应先排查再删除 |
| 系统目录元数据 | 已忽略 | Thumbs.db、Desktop.ini、.DS_Store |
| `.git/` | Git 自行管理 | 上传文件或打包源码时不另传 Git 内部文件 |

忽略不等于删除。本次只调整上传规则，没有清理用户配置、生成状态或报告。

## 本次检查结论

检查时 `.reports/`、`configs/`、打包 HTML、快照 JS 均未被 Git 跟踪，现有规则已生效；没有发现需要从 Git 索引移除的上述运行产物。本次补充编译文件、系统元数据及 PBRD 临时残留的忽略规则。

新增的模板和测试脚本应随功能修改一起提交。测试目录里有依赖当前 TXJ 产品配置、原版本和本机 ARMCC 的专项脚本；源码适合保留，但测试输入不随 configs 自动上传，不代表新机器可无条件运行全部测试。

当前 TXJ 产品 JSON 不会进入本工具仓库。它需要随产品交付时，请在产品仓库保存一份，或由使用者明确决定是否整理为公共示例，避免误以为提交 PBRD 已经提交板级配置。

## 提交前自检

在 pbrd 目录执行：

```powershell
git status --short
git status --short --ignored
git diff --stat
git diff --check
git ls-files .reports configs board-config-preview.html ui/platform-data.js
python -B scan-project.py
python -B ui/local_server.py --check
python -B ui/build_catalog.py
python -B ui/build_preview.py
```

`git ls-files` 对以上派生产物应为空。`.gitignore` 不会使已跟踪文件自动失效；若以后误加入，需要单独核对索引，但不要盲目删除本机状态文件。

查看完整差异后再按需要暂存、提交和推送。本文不代替产品代码和配置的版本管理，不包含自动提交操作。
