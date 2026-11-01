"""为并发测试运行提供相互隔离的配置管理实现。

本模块是现有 ``config.py`` 的独立替代方案。初始化脚本 ``init_env.py`` 使用本模块生成
构建专属配置快照；现有 pytest 流程尚未改为读取该快照。
与旧实现不同，导入本模块不会读取配置文件，也不会创建全局单例。调用方需要
显式创建 ``ConfigManager``，再加载基础 JSON 配置。每次加载都会产生一份独立、
只读的 ``Config`` 快照；本次构建传入的环境变量只覆盖该快照，不会修改共享的
基础配置文件。

基本使用步骤：

1. 创建配置管理器，并把 Jenkins 等构建环境提供的覆盖值传给它。
2. 管理器读取基础配置、合并覆盖值并校验配置结构，返回只读快照。
3. 将快照传给当前进程需要配置的组件。
4. 如果初始化程序和 pytest 在不同进程中运行，将快照写到当前构建专属的路径；
   后续进程从该路径加载。每个并发构建必须使用不同的输出路径。

示例（在构建初始化阶段）：

    import os
    from pathlib import Path
    from src.base.config_v2 import ConfigManager

    manager = ConfigManager()
    config = manager.load(
        env=os.getenv("ENV") or None,
        browser_type=os.getenv("BROWSER_TYPE") or None,
    )
    build_id = os.environ.get("BUILD_ID") or str(os.getpid())
    snapshot_path = Path("runtime-configs") / build_id / "conf.json"
    manager.write_snapshot(config, snapshot_path)

下游进程可以用 ``ConfigManager(config_path=snapshot_path)`` 读取同一构建的快照。
"""

import copy
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional, Union

from src.base.const import GlobalVar


class ConfigError(ValueError):
    """配置读取、结构校验或快照保存失败时抛出的异常。"""


def _freeze(value: Any) -> Any:
    """递归冻结 JSON 数据，避免调用方意外修改配置快照。

    字典转换为只读映射，列表转换为元组；JSON 标量值保持原样。
    """
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """把只读配置数据转换为可序列化的普通 Python 容器。

    该函数会递归复制映射和序列，调用方修改返回值不会影响原快照。
    """
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class Config:
    """
    一次配置加载得到的只读快照。

    快照保存经过校验的常用配置字段，同时保留 JSON 中其他未识别字段，
    方便后续扩展配置结构。实例创建后不提供原地修改操作；需要不同配置时，
    应重新加载一份快照并传入对应的覆盖值。
    """

    environment: str
    browser_type: str
    web_time_out: float
    log_period: int
    base_urls: Mapping[str, str]
    _data: Mapping[str, Any] = field(repr=False, compare=False)

    @property
    def ENV(self) -> str:
        """当前运行环境；使用旧配置接口的大写字段名，便于逐步迁移。"""
        return self.environment

    @property
    def BROWSER_TYPE(self) -> str:
        """当前浏览器类型；使用旧配置接口的大写字段名，便于逐步迁移。"""
        return self.browser_type

    @property
    def WEB_TIME_OUT(self) -> float:
        """Playwright 默认操作超时时间，单位为毫秒。"""
        return self.web_time_out

    @property
    def LOG_PERIOD(self) -> int:
        """日志保留天数。"""
        return self.log_period

    @property
    def BASE_URL(self) -> str:
        """当前运行环境对应的基础网址。"""
        return self.base_urls[self.environment]

    def to_dict(self) -> dict:
        """返回完整配置的可修改副本。

        返回值包含原 JSON 中的扩展字段，可直接交给 JSON 序列化器。
        修改副本不会改变当前只读快照。
        """
        return _thaw(self._data)


class ConfigManager:
    """读取、校验并可选地保存独立配置快照的管理器。

    管理器不使用单例，也不在实例中缓存可变配置；每次加载都根据文件内容和
    本次传入的覆盖值创建新的快照。并发构建可以各自创建管理器，并读取同一份
    只读基础配置，而不会互相覆盖环境设置。

    跨进程传递快照时，调用方应为每个构建指定独立的输出路径。原子写入能防止
    读取方看到只写了一半的文件，但不能防止多个构建同时写入同一个目标路径。
    """

    VALID_ENVIRONMENTS = frozenset({"DEV", "GO", "PRO"})
    VALID_BROWSERS = frozenset({"chrome", "firefox", "edge", "webkit"})

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        """创建管理器。

        参数：
            config_path: 基础配置或某个构建专属配置快照的路径。省略时使用项目
                默认配置路径。创建对象时不会立即读取文件。
        """
        self.config_path = Path(config_path or GlobalVar.CONFIG_PATH)

    def load(
        self,
        *,
        env: Optional[str] = None,
        browser_type: Optional[str] = None,
    ) -> Config:
        """读取配置文件、应用本次运行覆盖值并返回已校验的只读快照。

        覆盖值只写入返回的内存快照，不会修改读取的文件。未提供覆盖值时，使用
        JSON 文件中的配置。空字符串覆盖值视为未提供，方便直接传入可能为空的
        CI 环境变量。

        参数：
            env: 可选的运行环境覆盖值，例如从 Jenkins 的 ``ENV`` 变量读取。
            browser_type: 可选的浏览器类型覆盖值。

        返回：
            可供当前构建或进程使用的只读配置快照。

        异常：
            ConfigError: 配置文件无法读取、JSON 格式错误或配置项不符合要求时抛出。
        """
        try:
            with self.config_path.open("r", encoding="utf-8") as config_file:
                data = json.load(config_file)
        except FileNotFoundError as exc:
            raise ConfigError(f"配置文件不存在: {self.config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"配置文件不是有效 JSON: {self.config_path} ({exc})"
            ) from exc
        except OSError as exc:
            raise ConfigError(f"读取配置文件失败: {self.config_path} ({exc})") from exc

        return self._build_snapshot(data, env=env, browser_type=browser_type)

    def _build_snapshot(
        self,
        data: Any,
        *,
        env: Optional[str],
        browser_type: Optional[str],
    ) -> Config:
        """校验原始配置、规范化本次运行的值并构造快照。"""
        if not isinstance(data, dict):
            raise ConfigError("配置文件顶层必须是 JSON 对象")

        general = data.get("GENERAL")
        web_info = data.get("WEB_INFO")
        if not isinstance(general, dict):
            raise ConfigError("配置项 GENERAL 必须是 JSON 对象")
        if not isinstance(web_info, dict):
            raise ConfigError("配置项 WEB_INFO 必须是 JSON 对象")

        env_value = general.get("ENV", "DEV")
        if env is not None and not (isinstance(env, str) and not env.strip()):
            env_value = env
        browser_value = general.get("BROWSER_TYPE")
        if browser_type is not None and not (
            isinstance(browser_type, str) and not browser_type.strip()
        ):
            browser_value = browser_type

        active_env = self._normalize_choice(
            "ENV",
            env_value,
            self.VALID_ENVIRONMENTS,
            uppercase=True,
        )
        active_browser = self._normalize_choice(
            "BROWSER_TYPE",
            browser_value,
            self.VALID_BROWSERS,
            uppercase=False,
        )

        timeout = general.get("WEB_TIME_OUT")
        try:
            timeout_value = float(timeout)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConfigError("GENERAL.WEB_TIME_OUT 必须是大于 0 的数字") from exc
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout_value)
            or timeout_value <= 0
        ):
            raise ConfigError("GENERAL.WEB_TIME_OUT 必须是大于 0 的数字")

        log_period = general.get("LOG_PERIOD", 7)
        if (
            isinstance(log_period, bool)
            or not isinstance(log_period, int)
            or log_period < 0
        ):
            raise ConfigError("GENERAL.LOG_PERIOD 必须是非负整数")

        base_urls = {}
        for environment, settings in web_info.items():
            if not isinstance(environment, str) or not isinstance(settings, dict):
                raise ConfigError("WEB_INFO 中每个环境都必须对应一个 JSON 对象")
            normalized_environment = environment.strip().upper()
            if not normalized_environment:
                raise ConfigError("WEB_INFO 环境名称不能为空")
            if normalized_environment in base_urls:
                raise ConfigError(
                    f"WEB_INFO 中环境名称重复（忽略大小写）: {environment}"
                )

            base_url = settings.get("BASE_URL")
            if not isinstance(base_url, str) or not base_url.strip():
                raise ConfigError(f"WEB_INFO.{environment}.BASE_URL 必须是非空字符串")
            base_urls[normalized_environment] = base_url.strip()

        if active_env not in base_urls:
            raise ConfigError(f"WEB_INFO 中没有配置环境 {active_env} 的 BASE_URL")

        normalized_data = copy.deepcopy(data)
        normalized_data["GENERAL"]["ENV"] = active_env
        normalized_data["GENERAL"]["BROWSER_TYPE"] = active_browser
        normalized_data["GENERAL"]["WEB_TIME_OUT"] = timeout_value
        normalized_data["GENERAL"]["LOG_PERIOD"] = log_period

        return Config(
            environment=active_env,
            browser_type=active_browser,
            web_time_out=timeout_value,
            log_period=log_period,
            base_urls=MappingProxyType(dict(base_urls)),
            _data=_freeze(normalized_data),
        )

    @staticmethod
    def _normalize_choice(
        name: str,
        value: Any,
        allowed_values: frozenset,
        *,
        uppercase: bool,
    ) -> str:
        """检查一个字符串配置值是否属于允许集合，并统一大小写。

        参数：
            name: 配置项名称，用于生成清晰的错误提示。
            value: JSON 文件中的原值或本次运行的覆盖值。
            allowed_values: 当前配置项允许使用的值集合。
            uppercase: 为 True 时转成大写；为 False 时转成小写。

        返回：
            去除首尾空格并完成大小写规范化后的配置值。

        异常：
            ConfigError: 值不是字符串或不在允许集合中时抛出。
        """
        if not isinstance(value, str):
            raise ConfigError(f"{name} 必须是字符串，有效值为: {sorted(allowed_values)}")

        normalized = value.strip()
        normalized = normalized.upper() if uppercase else normalized.lower()
        if normalized not in allowed_values:
            raise ConfigError(f"无效的 {name}: {value!r}，有效值为: {sorted(allowed_values)}")
        return normalized

    def write_snapshot(self, config: Config, destination: Union[str, Path]) -> Path:
        """将快照原子写入构建专属 JSON 文件。

        函数先在目标目录中创建临时文件，完整写入并刷新内容后，再用原子替换
        更新目标文件。读取方不会看到半成品文件。输出路径不能与共享基础配置
        相同；并发构建必须使用不同的目标路径，否则最后完成的构建会覆盖前一个。

        参数：
            config: 已加载并通过校验的只读配置快照。
            destination: 当前构建专属的输出路径。建议路径中包含 CI 构建编号。

        返回：
            写入后的目标路径。

        异常：
            ConfigError: 目标路径不允许覆盖基础配置，或目录创建、写入、替换失败时抛出。
        """
        destination = Path(destination)
        try:
            if destination.resolve() == self.config_path.resolve():
                raise ConfigError("构建配置快照不能覆盖共享的基础配置文件")
        except OSError as exc:
            raise ConfigError(f"解析配置快照路径失败: {destination} ({exc})") from exc

        temp_path = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            file_descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=str(destination.parent),
            )
            temp_path = Path(temp_name)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as output_file:
                json.dump(config.to_dict(), output_file, indent=2, ensure_ascii=False)
                output_file.write("\n")
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(str(temp_path), str(destination))
            return destination
        except ConfigError:
            raise
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise ConfigError(f"写入构建配置快照失败: {destination} ({exc})") from exc
