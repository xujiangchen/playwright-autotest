# EnhancedLocator 设计与使用

本文对应 `src/pw_common/enhanced_locator.py`。`EnhancedLocator` 让业务页面可以在构造函数中保存一个可直接操作的定位器，同时集中实现项目需要的自定义行为。`BasePage.locator()` 是创建它的统一入口，见 [BasePage 设计与使用](base_page.md)。

## 为什么需要这一层

Playwright 原生 `Locator` 已经可以保存和重复使用，不需要像传统 Selenium 页面对象那样在每次操作前重新调用 `find_element()`。本类的主要用途是扩展项目特有的操作，同时尽量保留原生 Locator 的调用方式。

```python
class SearchPage(BasePage):
    def __init__(self):
        super().__init__()
        self.search_textarea = self.locator("#search", "搜索输入框")

    def search(self, text: str) -> None:
        self.search_textarea.fill(text)
        self.search_textarea.clear()  # 委托给 Playwright 原生 Locator.clear()
```

## 原生接口的委托与结果包装

`EnhancedLocator` 继承同步 Playwright 的 `Locator`，内部保存一个原生 Locator。访问成员时，实例自身的属性和本类定义的方法优先；其余普通方法和属性通过 `__getattribute__()` 委托给内部 Locator。新增自定义方法不需要再登记到固定名单中。

如果原生方法或属性返回新的 `Locator`，`_wrap_result()` 会把它包装成 `EnhancedLocator`。因此 `filter()`、`nth()`、`first`、`last` 等组合定位之后，仍可使用自定义操作。`all()` 显式返回 `EnhancedLocator` 列表。非 Locator 结果保持原生返回值。

```python
item = page.locator(".item").filter(has_text="目标").nth(0)
item.click(sleep_time=0.5)  # item 仍是 EnhancedLocator
```

`element_name` 可选，目前用于 `__str__()`，并随新包装的定位器保留；它目前不自动写入日志。

## 自定义操作与原生操作

- `click(sleep_time=0, **kwargs)` 调用原生 `click()`，按需等待指定秒数，然后返回自身。
- `click_and_open_tab(tab_name, popup_timeout=None, **click_kwargs)` 先等待当前页面的弹窗事件，再点击定位器；把新 Tab 以指定名称登记到浏览器池、切到前台，并返回原生 `Page`。`popup_timeout` 单位为毫秒。若点击没有打开新 Tab，会超时报错。该方法要求当前页面由浏览器池管理，且目标名称尚未被使用。
- `click_and_download(save_path=None, download_timeout=None, **click_kwargs)` 先监听当前页面的下载事件，再点击定位器。传入完整文件路径时会创建父目录，并等待下载完成后保存；返回原生 `Download` 对象。不传路径时只等待下载开始，文件仍由 Playwright 暂存，浏览器上下文关闭后会被清理。`download_timeout` 的单位为毫秒；原生 `click()` 的参数通过 `click_kwargs` 传入。
- `click_and_downloads(expected_count=None, save_dir=None, download_timeout=None, **click_kwargs)` 收集一次点击触发的下载事件，返回 `Download` 列表。指定 `expected_count` 时严格等待该数量，数量不足会在等待超时后报错；超过指定数量的事件不会被收集。不指定数量时，首次下载必须在 `download_timeout` 内出现，之后每收到一个新事件就重新计时，连续 3 秒没有新事件即返回。未指定 `download_timeout` 时，首次下载沿用 Playwright 默认超时；指定时它也限制整个收集过程。若网站延迟超过 3 秒才发起下一批下载，可能提前结束。传入保存目录时，会在建议文件名前加 `01_`、`02_` 等序号，避免同名文件覆盖，并等待各文件下载完成；不传目录时只等待下载开始。
- `fill(value, **kwargs)` 调用原生 `fill()` 并返回自身。
- `all()` 返回全部匹配项的增强定位器列表。
- 没有重写的方法，例如 `clear()`、`count()`，按 Playwright 原生签名和返回值执行。原生 `clear()` 返回 `None`，所以它不能继续链式调用。

`sleep_time` 使用 Python 的 `time.sleep()`，单位为秒；它是固定等待，不检查页面业务状态。需要等待元素就绪时，优先使用 Locator 自带的等待或断言能力。

```python
download = page.download_button.click_and_download(
    save_path="downloads/report.csv",
    download_timeout=30_000,
)
assert download.suggested_filename == "report.csv"

downloads = page.download_button.click_and_downloads(
    expected_count=3,
    save_dir="downloads",
    download_timeout=30_000,
)
assert len(downloads) == 3

# 下载数量未知时，最后一次下载事件后静默 3 秒即返回
downloads = page.download_button.click_and_downloads(save_dir="downloads")

# 点击后打开新 Tab；后续 Page Object 会复用刚刚弹出的页面
popup = page.details_button.click_and_open_tab("details")
details = DetailsPage(browser_key=page.browser_key, tab_name="details")
assert details.page is popup
details.close(return_to=page)
```

两个下载方法都监听定位器所属页面的下载事件。如果点击后由新弹出的页面发起下载，需要在弹出页面上等待其下载事件。
`click_and_open_tab()` 等待的是新 Tab 出现，不保证该页面的业务内容已就绪；需要时对返回的 `Page` 调用 `wait_for_load_state()` 或等待具体元素。

## 类型与维护边界

本类为了兼容原生 Locator 继承了 `Locator`，但自定义 `click()`、`fill()` 返回 `EnhancedLocator`，而原生方法返回 `None`。IDE 会提示重写方法的返回类型不匹配；这是链式调用设计与父类类型签名之间的已知差异。项目使用时需了解这点，不能把该提示理解为运行时异常。

委托实现依赖 Playwright 的 Locator 接口结构。升级 Playwright 后，应特别留意组合定位、传入其他 Locator 的方法以及自定义重写方法的行为。`EnhancedLocator` 仅包装返回值为 `Locator` 的结果；其他类型按原生 API 返回。
