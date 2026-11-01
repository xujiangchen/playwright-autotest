import time

import pytest

from src.pages.baidu_page import BaiduPage
from src.utils.logger import Logger


class TestDemo:

    @pytest.fixture(scope="class")
    def initial_operation(self, create_browser):
        print("初始化浏览器")

    def test_01(self):
        Logger.info("Test 01")
        baidu_page = BaiduPage()
        baidu_page.start()
        baidu_page.input_search_content("111")
        time.sleep(5)

    def test_03(self):
        Logger.info("Test 03")
        baidu_page = BaiduPage()
        baidu_page.input_search_content("222")
        time.sleep(5)
