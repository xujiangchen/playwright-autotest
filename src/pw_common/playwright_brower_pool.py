import threading
from enum import Enum
from typing import Dict, Optional, List, Union, Any, Callable

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright, Playwright

from src.base.config import config
from src.pw_common.debug_browser import ensure_debug_browser
from src.utils.logger import Logger

"""
增强版浏览器驱动池
支持一个浏览器内打开多个窗口/标签页
使用单例模式， 整个测试框架中只有一个浏览器管理器，所有地方访问的都是同一个浏览器池
使用的是Playwright中Browser的隔离机制实现一个Case中操作多个浏览器
"""


class BrowserType(Enum):
    """支持的浏览器类型枚举"""
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"
    CHROME = "chrome"  # 实际是Chromium的Chrome频道
    MSEDGE = "msedge"  # Microsoft Edge


class EnhancedBrowserPool:
    _instance = None  # 类变量，用于存储唯一的实例
    _lock = threading.Lock()  # 只保护单例创建和初始化

    # 单例模式
    def __new__(cls):
        with cls._lock:  # 加锁，确保多线程环境下只有一个线程能进入
            if cls._instance is None:  # 如果实例还不存在
                cls._instance = super().__new__(cls)  # 创建新实例
                cls._instance._initialized = False  # 设置初始化标志为False
            return cls._instance

    def __init__(self):
        with self._lock:
            if self._initialized:
                return

            # 真正的初始化代码（只执行一次）
            self._pool_lock = threading.RLock()  # 保护池内部状态
            self._playwright: Optional[Playwright] = None
            self._browsers: Dict[str, Browser] = {}  # 存储不同Key的浏览器实例
            self._contexts: Dict[str, BrowserContext] = {}  # 存储不同Key的浏览器上下文
            self._pages: Dict[str, List[Page]] = {}  # 存储每个Key的页面列表（多窗口）
            self._browser_types: Dict[str, BrowserType] = {}  # key -> BrowserType
            self._headless: Dict[str, bool] = {}  # key -> 启动时的无头模式设置
            self._cdp_keys: set[str] = set()

            self._initialized = True

    def start_playwright(self) -> Playwright:
        """启动 Playwright, 同步模式"""
        with self._pool_lock:
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            return self._playwright

    def create_browser(self,
                       key: str = "default",
                       browser_type: Union[BrowserType, str] = BrowserType.CHROMIUM,
                       headless: bool = False,
                       channel: Optional[str] = None,
                       **launch_options) -> Browser:
        """
       创建指定类型的浏览器

       Args:
           key: 浏览器唯一标识
           browser_type: 浏览器类型（枚举或字符串）
           headless: 是否无头模式
           channel: 浏览器渠道（chrome/msedge等）
           **launch_options: 额外启动参数

       Returns:
           Browser实例
       """
        with self._pool_lock:
            if key in self._browsers:
                raise ValueError(f"浏览器Key '{key}' 已存在！")

            if isinstance(browser_type, str):
                try:
                    browser_type = BrowserType(browser_type.strip().lower())
                except ValueError as exc:
                    valid_types = [t.value for t in BrowserType]
                    raise ValueError(
                        f"无效的浏览器类型: {browser_type}，有效类型: {valid_types}"
                    ) from exc
            elif not isinstance(browser_type, BrowserType):
                raise TypeError("browser_type 必须是 BrowserType 或浏览器类型字符串")
            if not isinstance(headless, bool):
                raise TypeError("headless 必须是布尔值")

            args = self._prepare_launch_args(browser_type, headless, channel, launch_options)
            started_here = self._playwright is None
            try:
                self.start_playwright()
            except Exception as exc:
                raise RuntimeError(f"启动 Playwright 失败，无法创建浏览器 '{key}': {exc}") from exc

            try:
                browser = self._launch_browser(browser_type, args)
            except Exception as exc:
                cleanup_error = None
                if started_here and not self._browsers and self._playwright is not None:
                    try:
                        self._playwright.stop()
                    except Exception as stop_exc:
                        cleanup_error = stop_exc
                    else:
                        self._playwright = None

                message = f"启动浏览器 '{key}' ({browser_type.value}) 失败: {exc}"
                if cleanup_error is not None:
                    message += f"；回收 Playwright 也失败: {cleanup_error}"
                raise RuntimeError(message) from exc

            self._browsers[key] = browser
            self._browser_types[key] = browser_type
            self._headless[key] = headless
            self._pages[key] = []

            Logger.info(
                "创建%s浏览器: '%s' (channel=%s)",
                browser_type.value,
                key,
                args.get("channel", "default"),
            )
            return browser

    def connect_debug_browser(self, key: str = "default", browser_type: str = "chrome") -> Browser:
        """连接本机调试浏览器，并复用它已有的默认 Context。"""
        with self._pool_lock:
            if key in self._browsers:
                raise ValueError(f"浏览器Key '{key}' 已存在！")
            port = ensure_debug_browser(browser_type)
            started_here = self._playwright is None
            self.start_playwright()
            browser = None
            try:
                browser = self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}", timeout=10000,
                )
                if not browser.contexts:
                    raise RuntimeError("CDP 浏览器没有默认 Context")
                context = browser.contexts[0]
                context.set_default_timeout(config.WEB_TIME_OUT)
            except Exception as exc:
                cleanup_errors = []
                if browser is not None:
                    try:
                        browser.close()
                    except Exception as cleanup_exc:
                        cleanup_errors.append(f"断开 CDP 连接失败: {cleanup_exc}")
                if started_here and not self._browsers:
                    try:
                        self._playwright.stop()
                    except Exception as cleanup_exc:
                        cleanup_errors.append(f"停止 Playwright 失败: {cleanup_exc}")
                    else:
                        self._playwright = None
                detail = f"；{'；'.join(cleanup_errors)}" if cleanup_errors else ""
                raise RuntimeError(f"连接调试浏览器 '{key}' (端口 {port}) 失败: {exc}{detail}") from exc

            self._browsers[key] = browser
            self._contexts[key] = context
            self._pages[key] = []
            self._browser_types[key] = BrowserType.CHROME if browser_type == "chrome" else BrowserType.MSEDGE
            self._headless[key] = False
            self._cdp_keys.add(key)
            Logger.info("连接调试浏览器: '%s' (端口=%s)", key, port)
            return browser

    @staticmethod
    def _prepare_launch_args(browser_type: BrowserType, headless: bool, channel: Optional[str], launch_options: dict) -> dict:
        """准备启动参数"""
        if channel is not None and browser_type not in [BrowserType.CHROMIUM, BrowserType.CHROME, BrowserType.MSEDGE]:
            raise ValueError(f"{browser_type.value} 不支持 channel 参数")

        args: dict[str, Any] = {"headless": headless, **launch_options}

        # 按浏览器引擎设置默认启动参数，避免把 Chromium 参数传给 Firefox/WebKit。
        if browser_type == BrowserType.FIREFOX:
            default_browser_args = ["-width=1920", "-height=1080"]
        elif browser_type in [BrowserType.CHROMIUM, BrowserType.CHROME, BrowserType.MSEDGE]:
            default_browser_args = [
                "--start-maximized",  # 启动时最大化
                "--disable-blink-features=AutomationControlled",  # 隐藏自动化特征
                "--disable-infobars",  # 禁用信息栏
                "--disable-notifications",  # 禁用通知
                "--no-sandbox",  # 在某些Linux环境需要
                "--disable-dev-shm-usage",  # 在某些Linux环境需要
            ]
        else:
            default_browser_args = []

        # 保留调用方传入的 args，并将其追加在默认参数之后，允许调用方覆盖同类开关。
        custom_browser_args = args.pop("args", None)
        if custom_browser_args is None:
            custom_browser_args = []
        if not isinstance(custom_browser_args, (list, tuple)) or not all(
            isinstance(value, str) for value in custom_browser_args
        ):
            raise TypeError("启动参数 args 必须是字符串列表或元组")
        args["args"] = [*default_browser_args, *custom_browser_args]

        # 设置渠道参数（只对Chromium系浏览器有效）
        if browser_type in [BrowserType.CHROMIUM, BrowserType.CHROME, BrowserType.MSEDGE]:
            if channel:
                args["channel"] = channel
            elif browser_type == BrowserType.CHROME:
                args["channel"] = "chrome"
            elif browser_type == BrowserType.MSEDGE:
                args["channel"] = "msedge"

        return args

    def _launch_browser(self, browser_type: BrowserType, launch_args: dict) -> Browser:

        """启动指定类型的浏览器"""

        if self._playwright is None:
            raise RuntimeError("Playwright 未初始化，请先调用 start_playwright()")

        # 定义浏览器启动器映射
        launcher_map: Dict[BrowserType, Callable[..., Browser]] = {
            BrowserType.CHROMIUM: self._playwright.chromium.launch,
            BrowserType.FIREFOX: self._playwright.firefox.launch,
            BrowserType.WEBKIT: self._playwright.webkit.launch,
            BrowserType.CHROME: self._playwright.chromium.launch,
            BrowserType.MSEDGE: self._playwright.chromium.launch,
        }

        # 获取启动器
        launcher = launcher_map.get(browser_type)
        if launcher is None:
            raise ValueError(f"不支持的浏览器类型: {browser_type}")

        return launcher(**launch_args)

    def new_page(self, key: str = "default", tab_name: Optional[str] = None) -> Page:
        """在指定浏览器中创建新标签页，可指定标签页名称"""
        with self._pool_lock:
            if key not in self._browsers:
                raise ValueError(f"浏览器Key '{key}' 不存在")
            if tab_name is not None and (not isinstance(tab_name, str) or not tab_name.strip()):
                raise ValueError("tab_name 必须是非空字符串")

            pages = self._get_open_pages(key)
            if tab_name is not None and any(
                getattr(page, '_tab_name', None) == tab_name for page in pages
            ):
                raise ValueError(f"浏览器 '{key}' 中已存在名称为 '{tab_name}' 的标签页")

            if key not in self._contexts:
                if self._headless[key]:
                    # 无头模式：使用固定viewport
                    context = self._browsers[key].new_context(
                        viewport={"width": 1920, "height": 1080},
                        ignore_https_errors=True
                    )
                else:
                    # 有头模式：使用no_viewport，让--start-maximized生效
                    context = self._browsers[key].new_context(
                        no_viewport=True,  # 关键！让窗口大小由系统决定
                        ignore_https_errors=True
                    )
                # 设置默认超时时间
                try:
                    context.set_default_timeout(config.WEB_TIME_OUT)
                except Exception as exc:
                    try:
                        context.close()
                    except Exception as close_exc:
                        raise RuntimeError(
                            f"设置浏览器 '{key}' 的页面超时失败: {exc}；回收 Context 也失败: {close_exc}"
                        ) from exc
                    raise
                self._contexts[key] = context

            page = self._contexts[key].new_page()
            self._register_page(key, page, tab_name)
            return page

    def _register_page(self, key: str, page: Page, tab_name: Optional[str]) -> None:
        if tab_name is not None:
            setattr(page, '_tab_name', tab_name)
        self._pages[key].append(page)
        page.on("close", lambda *_: self._remove_page(key, page))

    def _remove_page(self, key: str, page: Page) -> None:
        """页面关闭时从对应浏览器的记录中移除。"""
        with self._pool_lock:
            pages = self._pages.get(key)
            if pages is not None:
                self._pages[key] = [registered for registered in pages if registered is not page]

    def validate_popup_target(self, parent_page: Page, tab_name: str) -> str:
        """确认父页面受池管理且目标标签页名称可用，返回浏览器 Key。"""
        if not isinstance(tab_name, str) or not tab_name.strip():
            raise ValueError("tab_name 必须是非空字符串")

        with self._pool_lock:
            for key in self._pages:
                pages = self._get_open_pages(key)
                if not any(page is parent_page for page in pages):
                    continue
                if any(getattr(page, '_tab_name', None) == tab_name for page in pages):
                    raise ValueError(f"浏览器 '{key}' 中已存在名称为 '{tab_name}' 的标签页")
                return key

        raise ValueError("父页面未登记到浏览器池，无法登记新标签页")

    def register_popup(self, parent_page: Page, popup: Page, tab_name: str) -> None:
        """将已有的弹出页面登记到父页面所属浏览器，并赋予唯一标签页名称。"""
        with self._pool_lock:
            key = self.validate_popup_target(parent_page, tab_name)
            if popup.is_closed():
                raise RuntimeError("新标签页已关闭，无法登记")
            if popup.context is not self._contexts.get(key):
                raise ValueError("新标签页与父页面不属于同一个浏览器上下文")
            if any(page is popup for page in self._pages[key]):
                raise ValueError("新标签页已登记到浏览器池")

            setattr(popup, '_tab_name', tab_name)
            self._pages[key].append(popup)
            popup.on("close", lambda *_: self._remove_page(key, popup))

    def _get_open_pages(self, key: str) -> List[Page]:
        """清理已关闭页面的引用；调用方需持有 _pool_lock。"""
        pages = self._pages.get(key, [])
        open_pages = [page for page in pages if not page.is_closed()]
        if len(open_pages) != len(pages):
            self._pages[key] = open_pages
        return open_pages

    def get_or_create_page(self, key: str = "default", tab_name: str = "main_tab") -> Page:
        """获取指定浏览器中的命名标签页；不存在时创建。"""
        if not isinstance(tab_name, str) or not tab_name.strip():
            raise ValueError("tab_name 必须是非空字符串")

        with self._pool_lock:
            if key not in self._browsers:
                raise ValueError(f"浏览器Key '{key}' 不存在")

            for page in self._get_open_pages(key):
                if getattr(page, '_tab_name', None) == tab_name:
                    return page

            if key in self._cdp_keys and tab_name == "main_tab":
                existing = [page for page in self._contexts[key].pages if not page.is_closed()
                            and not any(page is registered for registered in self._pages[key])]
                if existing:
                    page = next((page for page in existing if page.url != "about:blank"), existing[0])
                    self._register_page(key, page, tab_name)
                    return page

            return self.new_page(key, tab_name=tab_name)

    def get_page(self, key: str = "default", page_index: Optional[int] = None, tab_name: Optional[str] = None) -> Page:
        """
        page_index 虽然在创建 page 的时候没有这个参数，但是创建 page 的时候其实是往 self._pages 这list 中添加，所以可以使用index 去获取，但是不建议
        """

        with self._pool_lock:
            # 检查浏览器是否存在
            if key not in self._browsers:
                raise ValueError(f"浏览器Key '{key}' 不存在")

            if page_index is not None and tab_name is not None:
                raise ValueError("page_index和tab_name不能同时提供，请只使用一个参数")

            # 检查页面列表是否存在
            pages = self._get_open_pages(key)
            if not pages:
                raise ValueError(f"浏览器 '{key}' 中暂无页面，请先调用new_page()创建页面")

            # 按名称查找
            if tab_name is not None:
                for page in pages:
                    name = getattr(page, '_tab_name', None)
                    if name == tab_name:
                        return page
                # 没找到对应的标签页名称
                available_names = []
                for page in pages:
                    if hasattr(page, '_tab_name'):
                        available_names.append(page._tab_name)

                error_msg = f"未找到名称为 '{tab_name}' 的标签页"
                if available_names:
                    error_msg += f"，可用名称: {available_names}"
                raise ValueError(error_msg)

            # 按索引查找（默认page_index=0）
            if page_index is None:
                page_index = 0

            # 检查索引是否有效
            if page_index < 0 or page_index >= len(pages):
                raise ValueError(
                    f"页面索引 {page_index} 超出范围。"
                    f"浏览器 '{key}' 共有 {len(pages)} 个页面，有效索引: 0-{len(pages) - 1}"
                )

            return pages[page_index]

    def close_page(self, key: str = "default", page_index: Optional[int] = None,
                   tab_name: Optional[str] = None) -> None:
        """关闭指定标签页，但保留该浏览器的最后一个标签页。"""
        if page_index is None and tab_name is None:
            raise ValueError("关闭标签页时必须提供 page_index 或 tab_name")

        with self._pool_lock:
            page = self.get_page(key, page_index=page_index, tab_name=tab_name)
            if len(self._get_open_pages(key)) == 1:
                raise RuntimeError(f"浏览器 '{key}' 只剩最后一个标签页，不能关闭")
            page.close()

    def get_browser_type(self, key: str) -> Optional[BrowserType]:
        """获取浏览器类型"""
        with self._pool_lock:
            return self._browser_types.get(key)

    def get_browser(self, key: str = "default") -> Optional[Browser]:
        """获取浏览器实例"""
        with self._pool_lock:
            return self._browsers.get(key)

    def close_browser(self, key: str) -> None:
        """关闭指定浏览器；关闭失败时保留引用，以便调用方重试。"""
        with self._pool_lock:
            if key in self._browsers:
                self._browsers[key].close()
                # 清理引用
                del self._browsers[key]
                self._contexts.pop(key, None)
                self._pages.pop(key, None)
                self._browser_types.pop(key, None)
                self._headless.pop(key, None)
                self._cdp_keys.discard(key)
                Logger.info("关闭浏览器: '%s'", key)

    def close_all(self) -> None:
        """尝试关闭所有资源；Playwright 停止失败时保留引用以便重试。"""
        errors: List[tuple[str, Exception]] = []
        with self._pool_lock:
            for key in list(self._browsers.keys()):
                try:
                    self.close_browser(key)
                except Exception as exc:
                    errors.append((f"浏览器 '{key}'", exc))
            playwright_stopped = True
            try:
                if self._playwright is not None:
                    self._playwright.stop()
            except Exception as exc:
                playwright_stopped = False
                errors.append(("Playwright", exc))
            if playwright_stopped:
                self._playwright = None
                self._browsers.clear()
                self._contexts.clear()
                self._pages.clear()
                self._browser_types.clear()
                self._headless.clear()
                self._cdp_keys.clear()
        if errors:
            details = "; ".join(f"{name}: {error}" for name, error in errors)
            raise RuntimeError(f"关闭浏览器池时发生错误：{details}") from errors[0][1]

    def get_all_keys(self) -> List[str]:
        """获取所有浏览器Key"""
        with self._pool_lock:
            return list(self._browsers.keys())

    def has_browser(self, key: str) -> bool:
        """检查浏览器是否存在"""
        with self._pool_lock:
            return key in self._browsers

    def get_page_count(self, key: str) -> int:
        """获取未关闭的页面数量"""
        with self._pool_lock:
            return len(self._get_open_pages(key))

    # 快捷方法
    def create_chrome(self, key: str = "default", **kwargs) -> Browser:
        """创建Chrome浏览器"""
        return self.create_browser(key, BrowserType.CHROME, **kwargs)

    def create_firefox(self, key: str = "default", **kwargs) -> Browser:
        """创建Firefox浏览器"""
        return self.create_browser(key, BrowserType.FIREFOX, **kwargs)

    def create_webkit(self, key: str = "default", **kwargs) -> Browser:
        """创建WebKit浏览器"""
        return self.create_browser(key, BrowserType.WEBKIT, **kwargs)

    def create_edge(self, key: str = "default", **kwargs) -> Browser:
        """创建Edge浏览器"""
        return self.create_browser(key, BrowserType.MSEDGE, **kwargs)


# 全局实例，方便导入使用
browser_pool = EnhancedBrowserPool()
