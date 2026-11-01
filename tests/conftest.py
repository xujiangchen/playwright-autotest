import os
import re
import uuid
from datetime import datetime

import allure
import pytest

from src.base.config import config
from src.base.const import GlobalVar
from src.pw_common.debug_browser import load_debug_config
from src.pw_common.playwright_brower_pool import browser_pool
from src.utils.logger import Logger


def _safe_log_name(name: str) -> str:
    """清理并限制用于日志文件名的 Case/Class 名称。"""
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return safe_name[:60].rstrip(" .") or "case"


def _restore_current_logger(logger):
    """恢复进入当前fixture前的logger上下文。"""
    if logger is None:
        Logger.clear_current_logger()
    else:
        Logger.set_current_logger(logger)


@pytest.fixture(scope="class", autouse=True)
def create_browser(request):
    """
    Class级别的浏览器夹具
    在一个测试类中只创建一次浏览器，所有测试方法共享
    测试类结束后自动销毁
    """
    browser_key = "default"
    class_owner = request.cls.__name__ if request.cls else request.node.module.__name__
    class_name = _safe_log_name(class_owner)
    run_suffix = uuid.uuid4().hex[:12]
    log_date = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(GlobalVar.LOG_FOLDER_PATH, log_date, f"{class_name}_{run_suffix}.log")
    logger_name = f"class_{run_suffix}"
    class_logger = Logger.get_logger(logger_name, log_file=log_file)
    previous_logger = Logger.get_current_logger()
    Logger.set_current_logger(class_logger)

    browser_creators = {
        "chrome": browser_pool.create_chrome,
        "firefox": browser_pool.create_firefox,
        "edge": browser_pool.create_edge,
        "webkit": browser_pool.create_webkit,
    }

    try:
        Logger.info("开启浏览器")
        browser_type = config.BROWSER_TYPE.lower()
        debug_config = load_debug_config()
        if debug_config["enabled"]:
            browser_pool.connect_debug_browser(key=browser_key, browser_type=browser_type)
        else:
            if browser_type not in browser_creators:
                raise ValueError(f"不支持的浏览器类型: {config.BROWSER_TYPE}")
            browser_creators[browser_type](key=browser_key, headless=False)

        yield browser_key
    finally:
        # 即使浏览器初始化失败，也清理可能已启动的资源并附加Class日志。
        try:
            browser_pool.close_all()
        finally:
            try:
                Logger.close_logger(logger_name)
            finally:
                _restore_current_logger(previous_logger)

            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                allure.attach(log_content, name=f"Class日志_{class_owner}", attachment_type=allure.attachment_type.TEXT)


@pytest.fixture(autouse=True)
def setup_test_logger(request):
    """自动为每个测试设置logger"""
    test_name = request.node.name
    safe_test_name = _safe_log_name(test_name)
    run_id = uuid.uuid4().hex
    run_suffix = run_id[:12]

    # 创建测试logger
    log_date = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(GlobalVar.LOG_FOLDER_PATH, log_date, f"{safe_test_name}_{run_suffix}.log")
    logger_name = f"case_{run_suffix}"
    logger = Logger.get_logger(logger_name, log_file=log_file)

    # Case日志临时覆盖Class logger；Case结束后恢复Class logger。
    previous_logger = Logger.get_current_logger()
    Logger.set_current_logger(logger)

    try:
        yield
    finally:
        # 先关闭文件handler，确保日志写入完成，再读取并附加到Allure。
        try:
            Logger.close_logger(logger_name)
        finally:
            _restore_current_logger(previous_logger)

        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            allure.attach(log_content, name=f"测试日志_{test_name}", attachment_type=allure.attachment_type.TEXT)
