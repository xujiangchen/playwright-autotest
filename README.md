# Playwright 自动化测试项目

使用 pytest 组织测试，Playwright 同步 API 操作浏览器，Allure 收集测试日志。项目采用页面对象封装：`src/pages/` 放具体页面，`src/pw_common/` 放浏览器池、基础页面和定位器封装。

## 安装

在项目根目录运行（PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chrome
```

如需使用 Firefox 或 WebKit，请安装对应的 Playwright 浏览器；使用 Edge 时需在系统中安装 Microsoft Edge。

## 配置

先复制示例配置，再编辑 `configs/conf.json` 的 `GENERAL` 配置：

```powershell
Copy-Item configs/conf.example.json configs/conf.json
```

- `BROWSER_TYPE`：`chrome`、`firefox`、`edge` 或 `webkit`。测试默认以有界面模式启动浏览器。
- `WEB_TIME_OUT`：Playwright 默认操作超时，单位为毫秒。
- `LOG_PERIOD`：运行 `init_env.py` 时保留日志的天数。
- `ENV`：当前环境名，可选 `DEV`、`GO`、`PRO`。

需要接管已打开的浏览器时，编辑 `configs/debug.json`：

```json
{"enabled": true, "port": 9222, "browser_started": false}
```

调试模式仅支持 `BROWSER_TYPE=chrome` 或 `edge`。运行测试时会检查本机端口上的 CDP 服务；若不存在，使用独立的 `.debug-browser-profile/` 启动浏览器，待端口就绪后将 `browser_started` 写为 `true` 并连接。该字段只是状态记录，浏览器被手动关闭后，下次运行会重新检查并启动。`BasePage` 的默认 `main_tab` 会复用默认 Context 中第一个非空白标签页；如有多个已打开的标签页，请先关闭或调整顺序，以免选中非目标页面。测试结束时会断开 Playwright 连接，浏览器窗口继续保留。关闭调试模式时把 `enabled` 改回 `false`。

运行 `init_env.py` 可清理过期日志，并通过 V2 配置管理器读取 `ENV`（兼容旧变量名 `EVN`）和 `BROWSER_TYPE` 环境变量，将本次运行配置保存为独立快照，不会改写 `configs/conf.json`。可以传入构建号；省略时使用初始化进程号：

```powershell
python init_env.py 12345
python init_env.py
```

脚本会输出 `BUILD_NUMBER=...`，也会从初始化函数返回实际使用的编号。快照保存在 `runtime-configs/<构建号>/conf.json`。**当前 pytest 仍从旧的 `src/base/config.py` 读取默认配置，不会自动加载这个快照。** 配置中的 `WEB_INFO` 保存各环境的基础地址；目前示例页面类使用各自写定的网址。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

生成 Allure 原始结果：

```powershell
.\.venv\Scripts\python.exe -m pytest --alluredir=allure-results
```

当前 `tests/test_demo.py` 包含两个百度页面示例测试，需要浏览器和网络连接。测试运行日志写入 `logs/`，并附加到 Allure 结果中。

## 完整目录结构

下面列出项目中需要维护的源码、配置和说明文件。运行环境与测试会另外生成 `.venv/`、`.pytest_cache/`、`logs/`、`allure-results/` 等目录，这些目录的内容不属于项目源码。

```text
playwright-autotest/
├── .gitignore                         # Git 忽略规则；当前会忽略 configs/conf.json
├── README.md                          # 项目说明、安装步骤、配置方法、运行方式和目录索引
├── init_env.py                        # 初始化脚本：使用 V2 配置管理器生成构建专属快照，并清理过期日志
├── pytest.ini                         # pytest 配置：指定测试目录及测试文件、类、函数的命名规则
├── requirements.txt                   # Python 依赖：Playwright、pytest 和 Allure pytest 插件
├── configs/
│   ├── __init__.py                    # 将 configs 标记为 Python 包
│   ├── debug.json                      # CDP 调试模式、端口和浏览器运行状态
│   ├── conf.example.json               # 可复制的运行配置示例
│   └── conf.json                      # 运行配置：环境、浏览器类型、超时、日志保留期和各环境基础地址
├── src/
│   ├── __init__.py                    # 将 src 标记为 Python 包
│   ├── base/
│   │   ├── __init__.py                # 将 src.base 标记为 Python 包
│   │   ├── config.py                  # ConfigManager 读写配置；Config 提供属性式配置访问
│   │   ├── config_v2.py               # 隔离式配置实现：显式加载、不可变快照、构建间配置隔离
│   │   └── const.py                   # 计算项目根目录、配置文件路径和日志目录路径
│   ├── pages/
│   │   ├── __init__.py                # 将 src.pages 标记为 Python 包
│   │   ├── baidu_page.py              # 百度页面对象：定位搜索框、打开百度、输入搜索内容
│   │   └── taobao_page.py             # 淘宝页面对象：定位搜索框、打开淘宝、输入搜索内容
│   ├── pw_common/
│   │   ├── __init__.py                # 将 src.pw_common 标记为 Python 包
│   │   ├── base_page.py               # 页面对象基类：获取或创建 Page、页面导航和基础操作
│   │   ├── debug_browser.py           # 检查、启动本机 CDP 调试浏览器
│   │   ├── enhanced_locator.py        # Locator 包装类：代理 Playwright 定位器操作，补充链式返回等行为
│   │   └── playwright_brower_pool.py  # 浏览器池：管理 Playwright、浏览器、上下文和多个页面
│   └── utils/
│       ├── __init__.py                # 将 src.utils 标记为 Python 包
│       ├── json_utils.py              # JSON 文件和字符串读写、校验、合并及路径取值工具
│       └── logger.py                  # 日志管理：创建 logger、文件/控制台输出、清理旧日志和 Allure 步骤
└── tests/
    ├── __init__.py                    # 将 tests 标记为 Python 包
    ├── conftest.py                    # pytest 共享夹具：按类创建/关闭浏览器，按 Case 建立并附加日志
    └── test_demo.py                   # 示例测试：演示创建百度页面对象并输入搜索内容
```

### 文件详解

#### config.py

**文件作用：** 管理项目配置的加载、内存访问、更新和持久化，为其他模块提供统一的配置入口。

这个文件中有两个主要部分：

- **`ConfigManager`：** 内部配置管理器，使用单例模式。模块初始化时读取 `configs/conf.json` 并把 JSON 内容存入内存；它负责维护配置状态以及和文件之间的同步，保存失败时会报告失败并恢复内存中的原值。**其他业务模块通常不直接操作它。**
- **`Config`：** 对外的配置访问接口。模块创建 `config = Config()`，其他模块通过这个对象读取配置，也通过它发起配置更新；底层的配置维护和文件同步由 `ConfigManager` 处理。

**默认执行流程：** 导入配置模块 → 创建唯一的配置管理器并读取 JSON 文件 → 创建对外的配置访问对象 → 其他模块通过 `config` 读取或更新配置 → 配置管理器维护内存状态并在更新时同步到文件。

这层封装将配置文件格式与业务代码隔开。新增配置项时，通常只需扩展配置数据和对应的访问入口，无需让业务模块直接读取或解析 JSON。

如果程序运行期间配置文件被外部修改，当前进程中的内存配置不会自动变化；需要显式重新加载才会读取外部变更。通常不建议在 Case 执行中重载，因为同一轮测试可能因此读取到不同配置，降低结果的一致性和可排查性。

### 运行时和生成目录

- `.venv/`：本地 Python 虚拟环境，由安装步骤创建。
- `.pytest_cache/`：pytest 自动生成的测试缓存。
- `logs/`：每个 Case 的文本日志，按日期放在子目录中。
- `allure-results/`：执行 `pytest --alluredir=allure-results` 后生成的 Allure 原始结果。
- `runtime-configs/`：采用新配置方案并在初始化进程与 pytest 进程间传递快照时使用；建议按构建编号分目录。
- `.idea/`：PyCharm 等 IDE 的本机项目设置。
- `.proxyai/`：本机工具配置目录，不属于测试框架的运行代码。

### 配置文件说明

`configs/conf.json` 当前被 `.gitignore` 忽略，因此它是本机配置文件；新克隆项目时需要自行准备该文件。配置字段由 `src/base/config.py` 读取，路径由 `src/base/const.py` 计算。

`init_env.py` 使用 `config_v2.ConfigManager` 读取基础配置，并把 `ENV`（或兼容的旧变量名 `EVN`）和/或 `BROWSER_TYPE` 的覆盖值保存到 `runtime-configs/<构建号>/conf.json`。构建号作为可选位置参数传入；未传时使用当前进程号。脚本函数会返回实际构建号，命令行会输出 `BUILD_NUMBER=...`。若配置无效或快照保存失败，脚本会以非零状态退出。

初始化脚本已经生成 V2 快照，但当前 pytest 仍通过 `src/base/config.py` 读取默认配置；后续还需让 pytest 的配置入口读取对应构建号目录中的快照，测试才会使用本次初始化的配置。
