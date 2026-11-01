# BasePage 设计与使用

本文对应 `src/pw_common/base_page.py`。`BasePage` 是同步 Playwright 项目的页面对象基类，负责将业务页面对象绑定到浏览器池中的具名 Tab，并提供项目常用的页面级操作。定位器的扩展行为见 [EnhancedLocator 设计与使用](enhanced_locator.md)；浏览器池的资源管理见 [浏览器池与 Tab 管理](browser_pool.md)。

## 设计思路

浏览器先由 `browser_pool` 创建。实例化 `BasePage` 或其子类时，构造函数调用 `get_or_create_page(browser_key, tab_name)`：同一浏览器下有同名且未关闭的 Tab 就复用，没有才创建。Page Object 的子类名称不参与查找，所以不同业务页面对象可以接力操作默认的 `main_tab`。需要同时保留多个 Tab 时，为它们指定不同的 `tab_name`。

`auto_activate=True` 是有意设置的默认值：取得 Tab 后调用 `bring_to_front()`，让有头浏览器显示该 Tab。构造时不需要切到前台，可以传 `auto_activate=False`；之后可显式调用 `activate()`。无论是否显示在前台，页面操作始终针对该对象绑定的 Playwright `Page`。

点击按钮弹出新 Tab 时，可调用定位器的 `click_and_open_tab("详情")`。新 Tab 会以该名称登记到浏览器池；随后实例化 `BasePage(tab_name="详情")` 或相应子类，会复用刚弹出的页面。`close(return_to=原页面对象)` 可在关闭新 Tab 后返回原 Tab。

```python
# 测试夹具已创建 default 浏览器
baidu = BaiduPage(tab_name="main_tab")
taobao = TaoBaoPage(tab_name="main_tab")
assert baidu.page is taobao.page  # 两个页面对象接力操作同一个 Tab

baidu = BaiduPage(tab_name="baidu")
taobao = TaoBaoPage(tab_name="taobao")  # 同时保留两个 Tab
```

## 页面生命周期

页面对象持有创建时取得的 `Page`，不会在 Tab 关闭后自动绑定新页面。`activate()`、`locator()`、导航和读取 URL、标题都会先检查页面是否关闭；对已关闭页面继续操作会抛出包含 `browser_key`、`tab_name` 的错误。已提前保存的 Locator 在后续执行操作时仍由 Playwright 报错。

`activate()` 切换失败时通过项目 `Logger` 记录异常，并以 `RuntimeError` 保留原异常作为原因，不会只打印提示后继续运行。

`close(return_to=...)` 用一个调用完成“关闭当前 Tab 并激活指定 Tab”。关闭操作走 `browser_pool.close_page()`，由池管理页面记录。关闭前会检查目标页面仍然打开，并拒绝把即将关闭的同一个 Tab 作为 `return_to`。浏览器只剩最后一个 Tab 时，浏览器池会拒绝关闭。关闭成功后，所有共享该 Tab 的旧页面对象均失效。

```python
a = BaiduPage(tab_name="a")
b = TaoBaoPage(tab_name="b")
b.close(return_to=a)  # 关闭 b，再把 a 切到前台
```

该“保留最后一个 Tab”规则适用于 `BasePage.close()` 和浏览器池的 `close_page()`。直接调用 `page.close()`、在浏览器窗口手动关闭 Tab，或关闭整个浏览器不受此规则约束。浏览器刚创建且尚未建立页面时，也可能暂时没有 Tab。

## 页面操作和定位器

`navigate()`、`reload()`、`go_back()`、`go_forward()` 调用同步 Playwright API，并返回当前 `BasePage` 对象，便于链式调用。底层导航响应不会通过这些方法返回；`go_back()`、`go_forward()` 没有可用历史记录时仍返回当前对象。需要响应内容时可直接使用 `self.page`。

`wait_until` 的类型 `NavigationWaitUntil` 限定为 `"load"`、`"domcontentloaded"`、`"commit"`、`"networkidle"`，默认 `"load"`。它只决定等待到哪个页面加载阶段，不表示业务元素已经就绪；类型标注用于静态检查，不做运行时校验。

`locator(selector, element_name=None)` 创建原生 Playwright Locator，再包装为 `EnhancedLocator`。业务页面可在构造函数中保存定位器，之后直接调用其操作方法：

```python
self.search_textarea = self.locator("//textarea[@id='chat-textarea']", "搜索输入框")
self.search_textarea.fill("关键词")
```

`BasePage` 不重复封装 Playwright 的全部页面能力；需要特定原生 `Page` 操作时可以使用 `self.page`。
