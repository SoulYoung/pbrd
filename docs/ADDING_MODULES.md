# 模块接入规范（供维护者和后续 AI 使用）

目标是从真实工程反推配置，不从旧表格猜接口。不得仅凭文件名把未知器件标记为完整支持。

## 工作步骤

1. 执行 `python -B scan-project.py`。阅读 `.reports/project-scan.json` 和 `.reports/MODULE_GAPS.md`。
2. 查看候选 per 的头文件、实现、所需总线、打开前必须设置的回调；查看实际 brd 结构体、cfg、def、src 和工程编译清单。
3. 区分用户必须输入的数据、平台可推导的资源、运行时参数和固定的生成器对象引用。目录存在不等于实际启用；工程里遗留的失效路径不作为支持证据。
4. 新器件补到对应 `modules/<模块>.json` 的 implementations 和 driver 选项。新 brd 模块新增同格式 JSON，文件名与 id 一致。
5. 添加或更新字段、默认值、依赖、source_globs 与 bus_kinds；记录实际来源和未审核限制。不要删除其他项目仍可能使用的定义。
6. 运行 `python -B ui/build_catalog.py`、`python -B ui/build_preview.py` 和扫描。新模块通过独立 JSON 自动进入页面，不应为普通字段再修改 app.js。
7. 验证新增实例、依赖变化、引脚复用、配置错误和 JSON 导出—导入一致性。旧 JSON 缺少新模块数组时补为空数组；未知已有模块不得静默丢弃。
8. 对生成器支持单独验收：模板输出、工程装配和编译验证。页面有配置字段不代表生成器已实现。

## 模块格式

- format: pbrd-module；schema_version: 1。
- id：小写模块名，匹配 JSON 文件名。
- name：中文说明。
- configuration_mode：instances（项目实例）或 platform（平台默认，无需空实例）。
- fields：key、label、type、value、opts。当前通用类型为 text、num、bool、select、gpio、adc、channel、signal、bus。
- dependencies：完整模块标识，如 drv.adc、brd.flash。
- implementations：value（器件选择值）、module（如 per.rtc.bm8563，内部实现可为 null）、bus_kinds、dependencies、source_globs。
- source_globs：项目相对路径，不能包含 .. 或指向项目外。用于判断实现存在，不执行源码。
- bus_kinds：iic、soft_iic、spi；无外部总线时为空。
- sources：生成目标和真实接口的证据路径。当前字段不代表代码生成已全部实现。

参考 analog.json、ext_rtc.json、flash.json。器件分类必须取实际实现层次：本项目 AT24 在 per/fram，SD NAND 在 per/mmc。

## 约束

保持 UTF-8、上下文代码风格；新增 C 接口尽量单出口。普通项目配置变化应进入项目 JSON，模块支持变化进入共享模块库。禁止自动运行扫描出的源码、删除原工程文件或把人工作出的未审核判断悄悄保存为平台事实。

当前生成入口为 generator/engine.py，已消费完整网页 JSON，不复制旧板级版本目录。

模板与模块映射的接入步骤：

1. 根据当前真实头文件与手写产物审核结构，不盲用 old/ 的旧接口。
2. 添加 templates/<平台>/ 中的文件或记录模板，遵循公共命名、注释和用户区格式。
3. 在 generator/modules/ 实现高层字段到模板上下文的映射，声明对象数量、共享资源、头文件和编译源码。
4. 更新 platforms/<mcu>-generation.json 的文件与工程成员清单；没有声明的实现不能被静默复制。
5. 需要从已有工程导入配置时，在 ui/project_preset.py 添加解析映射；该解析只用于生成输入，不作为运行时生成依赖。
6. 同步 modules/<模块>.json；configuration_status 区分 template-adapter 与 template-parameters。复杂模块先使用结构化模板参数，逐步完善高层表单。
7. 验证增删实例、共享总线引用、字段改变实际输出、用户区保留、无旧目录生成与编译。

源码风格修改在模板；对象关系在模块映射；通用格式在 generator/c_format.py；工程逻辑在 generator/projects/。不在 old/ 放新实现。

## 紧凑配置宏

analog、pwr_ctrl、misc_ctrl、uart 的重复数组项使用 INIT_* 宏。宏体放在正式 cfg 模板，generator/modules/compact.py 负责成员到参数的映射；参数名使用尾部下划线，避免与指定成员名发生预处理替换冲突。端口组、引脚和对象下标使用缩写，DMA、比例系数、回调和初始状态保留原值。结构化 JSON 格式不变，实例数量仍取输入长度。

新增字段需同步维护宏体和参数映射。遇到尚未纳入宏的成员或特殊对象引用，生成器保留该项的完整初始化结构，避免遗漏已有配置。维护者重新导入模板时保留已有 INIT_* 宏模板；接口变更需人工审核这些模板，并通过真实预处理展开对比及工程编译验证。

## 多产品参考与命名

新增高层适配位于 generator/modules/additional.py；平台 extensions 明确目标、头文件和源码。reference-only 表示扫描收录但尚不具备完整生成依据，应在网页阻止生成并说明缺失，不可填空 cfg 混过去。器件对象名保留芯片名称，同款多实例附序号；不要统一改成纯数字名称。注释参考原配置，集中在物理配置行，普通指针映射不重复写名称和引脚。

平台 configuration_macros 来自已审核 MCU 条件编译分支；有总线和设备分组，禁用能力注释保留在生成 cfg 中。模板也保留完整可选项；动态生成选中的器件宏后按清单整理，避免选项重复。

扫描出的内部实现必须标记 selection_mode=internal，不因发现 brd_*.c 就加入用户选择栏。default_enabled 只指定新建配置的默认选择，不能在重绘或恢复旧 JSON 时覆盖手动状态。器件实现可通过 enable_field 绑定布尔复选框；IC 卡同时保留当前平台公共实现所需的全量编译依赖，勾选只改变识别链中的对象。

## 新 MCU 与工具链

在 ui/source-settings.json.platforms 中增加平台来源，准备 platforms/<mcu>.json 引脚资源及对应 defaults、generation 规则；补充 templates/<mcu>/ 和平台对象映射。不能仅修改页面 MCU 列表。

复杂模块字段还需核对 ui/frontend-fields.json，避免覆盖模块库的新字段。修改来源后运行本地同步或重启服务。

工具链接入位于 generator/projects/，同时更新环境版本选项、输入校验和平台装配规则。先验证工程可打开及引用路径，再使用真实编译器验证 Boot/App。v0.0.1 的 IAR/CMake 仍需实现，不得只换工程后缀。
