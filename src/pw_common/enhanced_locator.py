import functools
import time
from pathlib import Path
from typing import Any, List, Optional, Union

from playwright.sync_api import Download, Locator, Page, TimeoutError as PlaywrightTimeoutError

from src.pw_common.playwright_brower_pool import browser_pool


class EnhancedLocator(Locator):
    """保留原生 Locator 接口，并为项目操作添加自定义行为。"""

    def __init__(self, locator: Locator, element_name: Optional[str] = None):
        self._locator = locator
        self.element_name = element_name

    def __getattribute__(self, name: str) -> Any:
        # 实例属性和自定义方法优先；Locator 自带的成员委托给原始对象。
        if name.startswith("__") and name.endswith("__"):
            return object.__getattribute__(self, name)
        if name in object.__getattribute__(self, "__dict__"):
            return object.__getattribute__(self, name)
        for cls in type(self).__mro__:
            if cls is Locator:
                break
            if name in cls.__dict__:
                return object.__getattribute__(self, name)

        raw_locator = object.__getattribute__(self, "_locator")
        attr = getattr(raw_locator, name)
        if not callable(attr):
            return self._wrap_result(attr)

        @functools.wraps(attr)
        def wrapper(*args, **kwargs):
            return self._wrap_result(attr(*args, **kwargs))
        return wrapper

    def _wrap_result(self, result: Any) -> Any:
        if isinstance(result, EnhancedLocator):
            return result
        if isinstance(result, Locator):
            return EnhancedLocator(result, self.element_name)
        return result

    def __str__(self) -> str:
        if self.element_name:
            return f"EnhancedLocator('{self.element_name}')"
        return f"EnhancedLocator({self._locator})"

    def __repr__(self) -> str:
        return f"<EnhancedLocator at {id(self)}>"

    def click(self, sleep_time: float = 0, **kwargs) -> 'EnhancedLocator':
        self._locator.click(**kwargs)
        if sleep_time:
            time.sleep(sleep_time)
        return self

    def click_and_open_tab(
        self,
        tab_name: str,
        *,
        popup_timeout: Optional[float] = None,
        **click_kwargs,
    ) -> Page:
        """点击并等待当前页面弹出新 Tab，将其登记为具名页面后返回。

        popup_timeout 单位为毫秒；不传时使用 Playwright 默认超时。
        返回的 Page 可直接操作，也可通过 BasePage(tab_name=tab_name) 复用。
        """
        parent_page = self._locator.page
        browser_pool.validate_popup_target(parent_page, tab_name)
        with parent_page.expect_popup(timeout=popup_timeout) as popup_info:
            self._locator.click(**click_kwargs)
        popup = popup_info.value
        browser_pool.register_popup(parent_page, popup, tab_name)
        popup.bring_to_front()
        return popup

    def click_and_download(
        self,
        save_path: Optional[Union[str, Path]] = None,
        *,
        download_timeout: Optional[float] = None,
        **click_kwargs,
    ) -> Download:
        """点击并等待当前页面触发下载，可将文件保存到指定路径。

        save_path 是包含文件名的完整路径；不传时仅返回 Download 对象。
        download_timeout 单位为毫秒；点击参数通过 click_kwargs 传给原生 click()。
        """
        download = self.click_and_downloads(
            expected_count=1,
            download_timeout=download_timeout,
            **click_kwargs,
        )[0]
        if save_path is not None:
            target = Path(save_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(target)
        return download

    def click_and_downloads(
        self,
        expected_count: Optional[int] = None,
        save_dir: Optional[Union[str, Path]] = None,
        *,
        download_timeout: Optional[float] = None,
        **click_kwargs,
    ) -> List[Download]:
        """点击并收集下载事件，可将文件保存到同一目录。

        指定 expected_count 时严格等待该数量的下载开始；不指定时，首次下载
        必须在 download_timeout 内出现，之后连续 3 秒没有新事件即结束。
        不传 save_dir 时只等待下载开始。保存时给建议文件名加序号前缀，
        避免同名文件相互覆盖。download_timeout 单位为毫秒；不指定时
        首次下载使用 Playwright 的默认超时；指定时也限制整个收集过程。
        """
        if expected_count is not None and (
            isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 1
        ):
            raise ValueError("expected_count 必须是大于 0 的整数")

        downloads: List[Download] = []
        page = self._locator.page

        if expected_count is not None:
            def collect_until_count(download: Download) -> bool:
                downloads.append(download)
                return len(downloads) >= expected_count

            with page.expect_download(
                predicate=collect_until_count,
                timeout=download_timeout,
            ):
                self._locator.click(**click_kwargs)
        else:
            idle_timeout_ms = 3_000
            last_download_at: Optional[float] = None
            deadline = (
                time.monotonic() + download_timeout / 1_000
                if download_timeout is not None and download_timeout > 0
                else None
            )

            def collect_download(download: Download) -> None:
                nonlocal last_download_at
                downloads.append(download)
                last_download_at = time.monotonic()

            page.on("download", collect_download)
            try:
                self._locator.click(**click_kwargs)
                if not downloads:
                    first_timeout = download_timeout
                    if deadline is not None:
                        first_timeout = (deadline - time.monotonic()) * 1_000
                        if first_timeout <= 0:
                            raise PlaywrightTimeoutError("等待首次下载事件超时")
                    page.wait_for_event("download", timeout=first_timeout)

                assert last_download_at is not None
                while True:
                    idle_remaining = idle_timeout_ms - (time.monotonic() - last_download_at) * 1_000
                    if idle_remaining <= 0:
                        break
                    wait_ms = idle_remaining
                    if deadline is not None:
                        total_remaining = (deadline - time.monotonic()) * 1_000
                        if total_remaining <= 0:
                            raise PlaywrightTimeoutError("等待下载事件结束超时")
                        wait_ms = min(wait_ms, total_remaining)
                    try:
                        page.wait_for_event("download", timeout=wait_ms)
                    except PlaywrightTimeoutError:
                        if deadline is not None and (deadline - time.monotonic()) * 1_000 <= 0:
                            raise PlaywrightTimeoutError("等待下载事件结束超时") from None
            finally:
                page.remove_listener("download", collect_download)

        if save_dir is not None:
            directory = Path(save_dir)
            directory.mkdir(parents=True, exist_ok=True)
            for index, download in enumerate(downloads, start=1):
                filename = Path(download.suggested_filename).name
                download.save_as(directory / f"{index:02d}_{filename}")
        return downloads

    def fill(self, value: str, **kwargs) -> 'EnhancedLocator':
        self._locator.fill(value, **kwargs)
        return self

    def all(self) -> List['EnhancedLocator']:
        """返回全部匹配项，并保持增强定位器类型。"""
        return [EnhancedLocator(loc, self.element_name) for loc in self._locator.all()]
