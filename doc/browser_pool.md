# 浏览器池与 Tab 管理

本文说明 `src/pw_common/playwright_brower_pool.py` 和 `src/pw_common/base_page.py` 的设计、使用方式及我们讨论过的边界情况。这里的 Tab 对应 Playwright 的 `Page` 对象，也可以是独立窗口中的页面。

## 一个管理器、多个浏览器、多个 Tab

`browser_pool` 是一个全局单例。它可以同时管理多个浏览器实例，用 `key` 区分，例如 `admin` 和 `member`。每个浏览器在首次创建 Tab 时建立自己的 `BrowserContext`，该浏览器的多个 Tab 共用这个 Context，因此共用登录状态；不同 `key` 的浏览器实例及 Context 相互独立。

假设 `admin` 和 `member` 各打开三个 Tab，内部状态大致如下。下列 `Browser(...)`、`Page(...)` 只是便于理解的示意值，不是对象的实际打印格式。

```python
_playwright = Playwright(...)  # 整个池共用一个 Playwright 驱动
_browsers = {
    "admin": Browser(...),
    "member": Browser(...),
}
_contexts = {
    "admin": BrowserContext(...),
    "member": BrowserContext(...),
}
_pages = {
    "admin": [Page("A1"), Page("A2"), Page("A3")],
    "member": [Page("B1"), Page("B2"), Page("B3")],
}
_browser_types = {"admin": BrowserType.CHROME, "member": BrowserType.CHROME}
_headless = {"admin": False, "member": False}
_pool_lock = threading.RLock()
```

`_pool_lock` 保护池中的字典、列表及资源创建和清理顺序；它不是“当前 Tab”指针。使用时按 `browser_key` 和 `tab_name` 明确定位页面。同步版 Playwright 对象本身不应据此视为可由多个线程任意并发操作；这里支持的是同一测试流程中同时持有并切换多个浏览器和 Tab。

## 创建和取得 Tab

```python
from src.pw_common.playwright_brower_pool import browser_pool

browser_pool.create_chrome("admin", headless=False)
browser_pool.create_chrome("member", headless=False)

admin_main = browser_pool.get_or_create_page("admin", tab_name="main_tab")
member_main = browser_pool.get_or_create_page("member", tab_name="main_tab")
admin_report = browser_pool.new_page("admin", tab_name="report")

# 两个浏览器可以分别有名为 main_tab 的 Tab。
# admin_main 与 member_main 的登录状态相互独立。
```

`tab_name` 是框架内用于查找 Tab 的名称，不是网页标题或 URL。名称只要求在**同一个浏览器的未关闭 Tab 中唯一**：

- `new_page(key, tab_name=...)` 明确创建新 Tab；同名 Tab 仍打开时抛出 `ValueError`，避免悄悄创建两个同名页面。
- `get_or_create_page(key, tab_name=...)` 找到同名且未关闭的 Tab 就返回它，否则创建。`BasePage` 使用此方法。
- `get_page(key, tab_name=...)` 只查找，不创建。底层也支持 `page_index`，但索引会随 Tab 关闭而变化，业务代码优先使用名称。
- 不传 `tab_name` 给 `new_page()` 可以创建匿名 Tab；匿名 Tab 可以按索引获取。
- `EnhancedLocator.click_and_open_tab(tab_name)` 会等待点击后弹出的 Tab，并通过 `register_popup()` 把它登记到父页面所属浏览器；后续可用相同 `tab_name` 创建 Page Object 来复用。

同名限制解决的是“框架不知道该返回哪一个 Tab”的歧义。它不会自动同步不同 Tab 中已加载的网页数据。比如管理员修改了会员资料，会员浏览器中的页面仍可能显示旧内容；完成修改后，应在会员页面 `reload()` 或重新触发查询，再检查结果。

## `BasePage` 与默认 `main_tab`

`BasePage(browser_key="default", tab_name="main_tab")` 会通过 `get_or_create_page()` 绑定 Tab。`BaiduPage` 和 `TaoBaoPage` 也使用这两个默认值，所以在同一个浏览器中依次实例化它们，会得到同一个 `main_tab`；之后的导航会在这个 Tab 中切换网站。若想保留两个网站各自的页面，给它们不同的 `tab_name`：

```python
from src.pages.baidu_page import BaiduPage
from src.pages.taobao_page import TaoBaoPage

baidu = BaiduPage(browser_key="admin", tab_name="baidu")
taobao = TaoBaoPage(browser_key="admin", tab_name="taobao")
```

两个 Page Object 绑定同一 `browser_key` 和 `tab_name` 时，操作的是同一个 Playwright `Page`，而不是各自新建一个 Tab。`BasePage` 不再用 `page_index` 自动取页；传入的 `tab_name` 就是查找和创建时使用的名称。参数错误会直接抛出，不会被当成“页面不存在”而重新建页。

## 关闭与状态清理

```python
browser_pool.close_page("admin", tab_name="report")  # 按名称关闭 Tab
browser_pool.close_browser("member")                 # 只关闭 member 浏览器
browser_pool.close_all()                              # 结束时清理整个池
```

每个由池创建的 Page 都注册了 `close` 事件回调。调用 `page.close()`、`close_page()`，或由浏览器关闭导致页面关闭时，回调会从 `_pages[key]` 移除该 Page。`close_page()` 会先确认目标存在，并拒绝关闭该浏览器的最后一个未关闭 Tab；随后调用 `page.close()`，由关闭事件移除记录。`BasePage.close()` 也走这个入口。直接调用 `page.close()` 或在浏览器窗口手动关闭 Tab 会绕过“保留最后一个 Tab”的限制。`get_page()`、`get_or_create_page()`、`new_page()` 和 `get_page_count()` 还会过滤已经关闭的 Page，作为关闭事件未及时更新记录时的兜底。关闭后，同一个 `tab_name` 可以重新创建。

`close_browser(key)` 关闭成功后删除该浏览器的记录；如果关闭抛错，会保留引用供调用方排查或重试。`close_all()` 会尝试关闭所有浏览器，再停止 Playwright，并汇总清理错误，不会因为第一个浏览器报错就跳过后续浏览器。Playwright 停止成功后，整个池的记录会清空；如果停止也失败，则保留剩余引用，以便再次处理。

## 启动参数与错误提示

`create_browser()` 接受 `BrowserType` 或不区分大小写的类型字符串。`create_chrome()`、`create_edge()`、`create_firefox()` 和 `create_webkit()` 是快捷方法。启动时会检查浏览器类型、`headless`、`channel` 与自定义 `args`；`args` 应为字符串列表或元组。自定义 `args` 会追加到默认启动参数之后。

浏览器启动失败时，异常会带上浏览器 `key`、类型及原始错误；若是该次调用刚启动的 Playwright，池还会尝试停止它。每个浏览器的 `headless` 值单独记录，用于首次建立 Context 时选择视口设置。运行中不要直接修改池的下划线字段。

## 测试夹具中的 `default` 浏览器

`tests/conftest.py` 的 class 级自动夹具会创建 `default` 浏览器，并在测试类结束时调用 `close_all()`。如果测试里再创建 `admin` 和 `member`，池中会有三个浏览器。只需两个浏览器时，可把 `default` 用作其中一个角色，或按测试需要调整夹具。`close_all()` 会关闭池中的所有浏览器，因此不要在还要继续使用它们时提前调用。

当 `configs/debug.json` 中的 `enabled` 为 `true` 时，夹具改为通过 CDP 连接 Chrome/Edge。浏览器池使用其默认 Context；首次获取 `main_tab` 时复用第一个非空白标签页，若没有已有页面则新建。`close_all()` 对 CDP 连接执行断开操作，不关闭独立启动或手工启动的浏览器；对普通 `launch()` 浏览器仍按原方式关闭。
