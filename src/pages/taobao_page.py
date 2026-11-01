from src.pw_common.base_page import BasePage


class TaoBaoPage(BasePage):

    def __init__(self, browser_key: str = "default", tab_name: str = "main_tab"):
        super().__init__(browser_key=browser_key, tab_name=tab_name)

        self.search_textarea = self.locator("//input[@id='q']")

    def start(self):
        self.navigate("https://www.taobao.com/")

    def input_search_content(self, content):
        self.search_textarea.fill(content)
