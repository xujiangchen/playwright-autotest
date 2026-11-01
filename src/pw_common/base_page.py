from typing import Literal, Optional

from playwright.sync_api import Page

from src.pw_common.enhanced_locator import EnhancedLocator
from src.pw_common.playwright_brower_pool import browser_pool
from src.utils.logger import Logger

NavigationWaitUntil = Literal["load", "domcontentloaded", "commit", "networkidle"]


class BasePage:
    """
    基础Page类，按浏览器Key和标签页名称绑定标签页。

    相同 browser_key 和 tab_name 始终绑定同一个未关闭的标签页，即使
    Page Object 属于不同的子类。默认的 main_tab 因此可供不同页面对象
    接力操作；需要同时保留多个标签页时，应为它们指定不同的 tab_name。
    标签页关闭后，此对象失效；后续操作会报错，不会自动绑定新标签页。
    """

    def __init__(self, browser_key: str = "default", tab_name: str = "main_tab", *, auto_activate: bool = True):
        """获取或创建指定标签页。

        Args:
            browser_key: 已创建的浏览器在浏览器池中的标识。
            tab_name: 标签页名称；同一浏览器下，同名的未关闭标签页会被复用，
                与 Page Object 的子类无关；不存在时才创建新标签页。
            auto_activate: 是否在获取标签页后将其切换到浏览器前台，默认开启。
        """
        self.browser_key = browser_key
        self.tab_name = tab_name
        self.page: Page = browser_pool.get_or_create_page(browser_key, tab_name=tab_name)
        if auto_activate:
            self.activate()

    def activate(self) -> 'BasePage':
        """将当前标签页切换到前台；失败时抛出 RuntimeError。"""
        try:
            self._ensure_page_open()
            self.page.bring_to_front()
        except Exception as exc:
            Logger.exception(
                "激活标签页失败 (browser_key=%r, tab_name=%r)",
                self.browser_key,
                self.tab_name,
            )
            raise RuntimeError(
                f"激活标签页失败 (browser_key={self.browser_key!r}, tab_name={self.tab_name!r}): {exc}"
            ) from exc
        return self

    def close(self, *, return_to: Optional['BasePage'] = None) -> None:
        """关闭当前标签页，并可将指定页面对象对应的标签页切到前台。

        浏览器只剩当前标签页时会报错，不执行关闭。
        关闭后，当前页面对象以及共享此标签页的其他页面对象均失效。
        """
        self._ensure_page_open()
        if return_to is not None:
            if return_to.page is self.page:
                raise ValueError("return_to 不能指向当前要关闭的标签页")
            return_to._ensure_page_open()

        browser_pool.close_page(key=self.browser_key, tab_name=self.tab_name)
        if return_to is not None:
            return_to.activate()

    def _ensure_page_open(self) -> None:
        """关闭后的 Page Object 不再允许操作。"""
        if self.page.is_closed():
            raise RuntimeError(f"标签页已关闭 (browser_key={self.browser_key!r}, tab_name={self.tab_name!r})")

    def locator(self, selector: str, element_name: Optional[str] = None) -> EnhancedLocator:
        """创建增强的Locator"""
        self._ensure_page_open()
        raw_locator = self.page.locator(selector)
        return EnhancedLocator(raw_locator, element_name)

    # 页面操作
    def navigate(self, url: str, wait_until: NavigationWaitUntil = "load") -> 'BasePage':
        """导航到指定 URL，并在所选加载阶段完成后返回当前页面对象。

        wait_until 默认为 load；加载阶段完成不代表业务元素已就绪。
        Playwright 的导航响应不会通过此方法返回。
        """
        self._ensure_page_open()
        self.page.goto(url, wait_until=wait_until)
        return self

    def reload(self, wait_until: NavigationWaitUntil = "load") -> 'BasePage':
        """重新加载当前页，等待指定加载阶段后返回当前页面对象。"""
        self._ensure_page_open()
        self.page.reload(wait_until=wait_until)
        return self

    def go_back(self, wait_until: NavigationWaitUntil = "load") -> 'BasePage':
        """尝试后退并等待指定加载阶段；即使没有历史记录也返回当前页面对象。"""
        self._ensure_page_open()
        self.page.go_back(wait_until=wait_until)
        return self

    def go_forward(self, wait_until: NavigationWaitUntil = "load") -> 'BasePage':
        """尝试前进并等待指定加载阶段；即使没有历史记录也返回当前页面对象。"""
        self._ensure_page_open()
        self.page.go_forward(wait_until=wait_until)
        return self

    def get_url(self) -> str:
        self._ensure_page_open()
        return self.page.url

    def get_title(self) -> str:
        self._ensure_page_open()
        return self.page.title()
