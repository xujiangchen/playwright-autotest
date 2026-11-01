# Debug 模式：接管 Chrome 或 Edge

Debug 模式通过 Chrome DevTools Protocol（CDP）连接本机浏览器。它适合复用已打开的窗口、标签页和登录状态，方便在测试结束后继续手工查看页面。该模式只作用于 `tests/conftest.py` 自动创建的 `default` 浏览器；测试代码主动调用浏览器池的普通 `create_*()` 方法时，仍按原有方式启动浏览器。

## 开启与运行

先将 `configs/conf.json` 中的 `GENERAL.BROWSER_TYPE` 设为 `chrome` 或 `edge`。然后编辑 `configs/debug.json`：

```json
{
  "enabled": true,
  "port": 9222,
  "browser_started": false
}
```

在项目根目录运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_demo.py
```

`enabled` 控制是否使用 CDP；设为 `false` 时，夹具按普通模式启动并关闭浏览器。`port` 是本机调试端口，必须是 1–65535 的整数。`browser_started` 由程序维护，通常无需手动修改。三个字段都必须存在，两个状态字段必须是 JSON 布尔值 `true` 或 `false`。

## 启动和连接流程

1. 访问 `http://127.0.0.1:<port>/json/version`，检查该端口是否提供 CDP 服务。即使 `browser_started` 是 `true`，也会重新检查实际状态。
2. 若已有可用的 CDP 服务，更新 `browser_started` 为 `true` 并直接连接。若端口被其他服务占用，立即报错。
3. 若端口空闲，查找本机 Chrome 或 Edge，以配置端口和独立的 `.debug-browser-profile/` 启动。程序最多等待 15 秒，确认 CDP 服务就绪后将 `browser_started` 写为 `true`。
4. 使用 Playwright 的 `chromium.connect_over_cdp()` 连接浏览器，并把连接登记到浏览器池。

浏览器被手动关闭后，JSON 中的 `browser_started` 可能暂时仍是 `true`；下次运行会将其修正为 `false` 并尝试重新启动。程序自动启动的浏览器使用独立 profile，登录状态会保存在 `.debug-browser-profile/`，该目录已被 Git 忽略。手工启动的浏览器只要在相同端口提供 CDP 服务，也可以被连接。

## 标签页和测试结束后的状态

CDP 连接使用浏览器已有的默认 `BrowserContext`。第一次获取默认的 `main_tab` 时，浏览器池选择其中第一个 URL 不为 `about:blank` 的未关闭标签页；如果只有空白页，则选第一个空白页；如果没有标签页，就创建一个。多个非空白标签页同时存在时，请先确认第一个就是要操作的页面。其他 `tab_name` 仍会按需创建新标签页。

测试类结束时，夹具调用 `browser_pool.close_all()`。对通过 CDP 连接取得的 `Browser`，Playwright 的 `browser.close()` 会断开连接，保留浏览器窗口；普通 `launch()` 创建的浏览器则会被关闭。测试期间对已有页面进行的导航和操作不会自动撤销，手动关闭的标签页也不会恢复。

## 常见问题

| 现象 | 检查项 |
| --- | --- |
| 提示仅支持 Chrome 或 Edge | 检查 `configs/conf.json` 的 `GENERAL.BROWSER_TYPE`。 |
| 找不到浏览器可执行文件 | 安装相应浏览器，或将可执行文件加入 `PATH`。 |
| 端口已被占用，但不是 CDP 服务 | 更换 `port`，或关闭占用该端口的程序。 |
| 连接到了非目标标签页 | 检查默认 Context 中标签页的顺序；`main_tab` 会选第一个非 `about:blank` 页面。 |
| 浏览器启动后立即退出或等待超时 | 确认所选端口可用，并检查 `.debug-browser-profile/` 是否已被另一个浏览器进程占用。 |

CDP 连接仅支持 Chromium 系浏览器，其功能范围与 Playwright 原生启动方式可能存在差异。参见 [Playwright 的 `connect_over_cdp()` 文档](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)和 [Chrome 的远程调试说明](https://developer.chrome.com/blog/remote-debugging-port/)。
