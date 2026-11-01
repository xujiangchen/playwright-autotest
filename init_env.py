"""初始化一次测试构建并保存它专属的配置快照。"""

import argparse
import os
import re
from pathlib import Path
from typing import Optional

from src.base.config_v2 import ConfigManager
from src.base.const import GlobalVar
from src.utils.logger import Logger


def _resolve_build_number(build_number: Optional[str]) -> str:
    """返回有效的构建号；未提供时使用当前进程号。"""
    if build_number is None or not build_number.strip():
        return str(os.getpid())

    build_number = build_number.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", build_number):
        raise ValueError(
            "构建号只能包含英文字母、数字、点、下划线和连字符，且必须以字母或数字开头"
        )
    if build_number.endswith("."):
        raise ValueError("构建号不能以点结尾")

    return build_number


def initialize_environment(build_number: Optional[str] = None) -> str:
    """加载 V2 配置、清理旧日志并保存构建专属快照。

    参数：
        build_number: 可选的构建号，用作快照目录名。省略或传入空字符串时，
            使用当前 Python 进程号。

    返回：
        实际使用的构建号；如果调用方未提供，则为当前进程号。
    """
    resolved_build_number = _resolve_build_number(build_number)

    manager = ConfigManager()
    config = manager.load(
        env=os.getenv("ENV") or os.getenv("EVN") or None,
        browser_type=os.getenv("BROWSER_TYPE") or None,
    )

    Logger.cleanup_old_logs(days=config.LOG_PERIOD)

    snapshot_path = (
        Path(GlobalVar.PROJECT_BASE_PATH)
        / "runtime-configs"
        / resolved_build_number
        / "conf.json"
    )
    manager.write_snapshot(config, snapshot_path)

    print(f"[INFO] 构建配置快照已保存：{snapshot_path}")
    return resolved_build_number


def main(argv: Optional[list] = None) -> str:
    """解析命令行参数并执行初始化。"""
    parser = argparse.ArgumentParser(description="初始化测试配置并保存构建快照")
    parser.add_argument(
        "build_number",
        nargs="?",
        help="可选构建号；省略时使用当前进程号",
    )
    args = parser.parse_args(argv)

    resolved_build_number = initialize_environment(args.build_number)
    print(f"BUILD_NUMBER={resolved_build_number}")
    return resolved_build_number


if __name__ == "__main__":
    # 命令行进程的退出码表示成功或失败；构建号通过 stdout 输出。
    main()
