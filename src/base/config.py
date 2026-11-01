import json
from typing import Any, Dict

from src.base.const import GlobalVar


class ConfigManager:
    """
    配置管理器 - 单例模式
    负责加载、读取和更新 configs 目录下的配置文件。
    """

    _instance = None
    _config = None
    _config_path = GlobalVar.CONFIG_PATH

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化配置管理器"""
        if self._config is None:
            self.load_config()

    def load_config(self):
        """加载配置文件中的基础配置"""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            print(f'[INFO] 加载配置文件成功：{self._config_path}')
            return self._config
        except FileNotFoundError:
            raise FileNotFoundError(f"❌ 配置文件不存在: {self._config_path}")
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"❌ 配置文件格式错误: {e}", e.doc, e.pos)

    def reload(self):
        """重新加载配置文件"""
        self._config = None
        return self.load_config()

    def set_env(self, env: str) -> bool:
        """
        修改运行环境配置
        
        Args:
            env: 环境名称 (DEV/GO/PRO)
            
        Returns:
            bool: 修改是否成功
            
        """
        valid_envs = ["DEV", "GO", "PRO"]
        if not isinstance(env, str):
            print(f"❌ 环境值必须是字符串，有效值为: {valid_envs}")
            return False
        env = env.upper()

        if env not in valid_envs:
            print(f"❌ 无效的环境值: {env}，有效值为: {valid_envs}")
            return False

        return self._update_general_setting("ENV", env, "环境")

    def set_browser_type(self, browser_type: str) -> bool:
        """
        修改浏览器类型配置

        Args:
            browser_type: 浏览器类型 (chrome/firefox/edge/webkit)
            
        Returns:
            bool: 修改是否成功
        """
        valid_browsers = ["chrome", "firefox", "edge", "webkit"]
        if not isinstance(browser_type, str):
            print(f"❌ 浏览器类型必须是字符串，有效值为: {valid_browsers}")
            return False
        browser_type = browser_type.lower()

        if browser_type not in valid_browsers:
            print(f"❌ 无效的浏览器类型: {browser_type}，有效值为: {valid_browsers}")
            return False

        return self._update_general_setting("BROWSER_TYPE", browser_type, "浏览器类型")

    def _update_general_setting(self, key: str, value: str, label: str) -> bool:
        """更新 GENERAL 配置项并持久化；保存失败时恢复原内存值。"""
        try:
            if self._config is None:
                self.load_config()

            general_config = self._config["GENERAL"]
            existed = key in general_config
            previous_value = general_config.get(key)
            general_config[key] = value

            if not self._save_config():
                if existed:
                    general_config[key] = previous_value
                else:
                    general_config.pop(key, None)
                print(f"❌ 保存{label}配置失败，已恢复内存中的原值")
                return False

            print(f"✅ 成功设置{label}: {value}")
            return True
        except Exception as e:
            print(f"❌ 设置{label}失败: {e}")
            return False

    def _save_config(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            bool: 保存是否成功
        """
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ 保存配置文件失败: {e}")
            return False

    @property
    def config(self) -> Dict:
        """获取配置字典"""
        if self._config is None:
            self.load_config()
        return self._config


# 创建模块级配置管理器。首次初始化时读取配置文件，之后的属性访问使用内存中的配置。
_config_manager = ConfigManager()


class Config:
    """
    配置常量类 - 通过属性访问配置
    配置访问 helper。它把内存中的嵌套字典包装成更方便的属性
    """

    @classmethod
    def _get(cls, key: str, default: Any = None) -> Any:
        """获取配置值"""
        try:
            keys = key.split('.')
            value = _config_manager.config
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            if default is not None:
                return default
            raise AttributeError(f"配置项 '{key}' 不存在")

    @property
    def ENV(self) -> str:
        """运行环境"""
        return self._get('GENERAL.ENV', "DEV")

    @property
    def BROWSER_TYPE(self) -> str:
        """浏览器类型"""
        return self._get('GENERAL.BROWSER_TYPE')

    @property
    def WEB_TIME_OUT(self) -> float:
        """默认等待时长"""
        return self._get('GENERAL.WEB_TIME_OUT')

    @property
    def LOG_PERIOD(self) -> int:
        """运行环境"""
        return self._get('GENERAL.LOG_PERIOD', 7)

    @property
    def BASE_URL(self) -> str:
        """基础URL"""
        return self._get(f'WEB_INFO.{self.ENV}.BASE_URL')

    @classmethod
    def set_env(cls, env: str) -> bool:
        """
        修改运行环境配置（类方法便捷调用）
        
        Args:
            env: 环境名称 (DEV/GO/PRO)
            
        Returns:
            bool: 修改是否成功
        """
        return _config_manager.set_env(env)

    @classmethod
    def set_browser_type(cls, browser_type: str) -> bool:
        """
        修改浏览器类型配置（类方法便捷调用）
        
        Args:
            browser_type: 浏览器类型 (chrome/firefox/edge/webkit)
            
        Returns:
            bool: 修改是否成功
        """
        return _config_manager.set_browser_type(browser_type)


# 创建模块级配置访问实例
config = Config()
