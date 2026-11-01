# Playwright 自动化测试项目

基于 Python、pytest 和 Playwright 同步 API 的网页自动化测试项目。页面操作封装在 `src/pages/`，浏览器、页面和定位器的通用能力放在 `src/pw_common/`；测试日志可附加到 Allure 结果中。

## 快速开始

以下命令适用于 Windows PowerShell。在准备存放项目的目录中依次执行：

```powershell
git clone https://github.com/xujiangchen/playwright-autotest.git
cd playwright-autotest
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chrome
Copy-Item configs/conf.example.json configs/conf.json
.\.venv\Scripts\python.exe -m pytest
```

默认配置使用 Chrome，以可见窗口运行测试。`tests/test_demo.py` 中的两个示例会访问百度，因此需要本机浏览器和网络连接。若已在项目目录中，跳过 `git clone` 和 `cd` 两行。

## 配置浏览器与环境

本机配置文件是 `configs/conf.json`，从 `configs/conf.example.json` 复制后按需修改。它已被 Git 忽略，不会随提交上传。

| 字段 | 作用 |
| --- | --- |
| `GENERAL.BROWSER_TYPE` | `chrome`、`firefox`、`edge` 或 `webkit`；测试以可见窗口运行。 |
| `GENERAL.WEB_TIME_OUT` | Playwright 操作的默认超时，单位为毫秒。 |
| `GENERAL.LOG_PERIOD` | 执行 `init_env.py` 时保留日志的天数。 |
| `GENERAL.ENV` | 当前环境：`DEV`、`GO` 或 `PRO`。 |
| `WEB_INFO` | 各环境的基础地址；当前示例页面仍使用代码中写定的网址。 |

使用其他浏览器时，先在配置中修改 `BROWSER_TYPE`，再安装对应浏览器：

```powershell
.\.venv\Scripts\python.exe -m playwright install firefox
.\.venv\Scripts\python.exe -m playwright install webkit
```

使用 `edge` 时，需在系统中安装 Microsoft Edge。以上浏览器只需安装实际要使用的一个。

## 运行测试与查看结果

运行全部测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

运行示例文件并生成 Allure 原始结果：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo.py --alluredir=allure-results
```

测试日志写入 `logs/`，并附加到 Allure 结果。要在本机打开可视化报告，需另行安装 [Allure 命令行工具](https://allurereport.org/docs/install/)；安装后运行 `allure serve allure-results`。`logs/` 和 `allure-results/` 都是运行生成目录，已被 Git 忽略。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `tests/` | pytest 测试和浏览器、日志夹具。 |
| `src/pages/` | 百度、淘宝的示例页面对象。 |
| `src/pw_common/` | 浏览器池、基础页面、定位器和调试浏览器连接。 |
| `src/base/` | 配置读取与运行时配置快照。 |
| `src/utils/` | 日志和 JSON 工具。 |
| `configs/` | 示例配置与调试浏览器配置。 |
| `doc/` | 各模块的详细设计说明。 |

## 详细文档

`doc/` 目录提供各模块更详细的使用说明和指导。需要了解具体配置、接口或实现方式时，可按主题阅读：[配置](doc/config.md) · [浏览器池](doc/browser_pool.md) · [Debug 模式](doc/debug_mode.md) · [基础页面](doc/base_page.md) · [增强定位器](doc/enhanced_locator.md) · [日志](doc/logger.md)。

## 进阶：连接调试浏览器

需要复用通过 CDP 打开的 Chrome 或 Edge 时，将 `configs/debug.json` 的 `enabled` 设为 `true`，并确保 `configs/conf.json` 中的 `BROWSER_TYPE` 为 `chrome` 或 `edge`。默认调试端口是 `9222`。

运行测试时，程序会先检查该端口；若没有可用的 CDP 浏览器，会使用独立的 `.debug-browser-profile/` 启动一个。`browser_started` 是程序维护的状态字段。调试模式会复用浏览器默认 Context 中第一个非空白标签页；若打开了多个标签页，请确认其顺序。测试结束后会断开连接，浏览器窗口继续保留。退出调试模式时将 `enabled` 改回 `false`。

详细配置、连接流程和排查方法见 [Debug 模式文档](doc/debug_mode.md)。

## 进阶：生成构建配置快照

`init_env.py` 可清理过期日志，并读取 `ENV`（兼容旧变量名 `EVN`）和 `BROWSER_TYPE` 环境变量，生成独立的配置快照：

```powershell
.\.venv\Scripts\python.exe init_env.py 12345
```

快照保存在 `runtime-configs/12345/conf.json`。省略构建号时使用当前初始化进程的进程号，命令会输出实际的 `BUILD_NUMBER`。**当前 pytest 仍通过 `src/base/config.py` 读取 `configs/conf.json`，不会自动使用该快照。**
