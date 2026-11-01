import atexit
import logging
import sys
import threading
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any

import allure


class Logger:
    """
    通用日志管理器
    提供基础的日志创建和管理功能，支持隐式调用
    """

    _lock = threading.Lock()
    _loggers: Dict[str, logging.Logger] = {}
    _thread_local = threading.local()
    _cleanup_registered = False

    @classmethod
    def get_logger(cls, name: Optional[str] = None,
                   log_file: Optional[str] = None,
                   log_level: str = "INFO",
                   console_output: bool = True,
                   max_bytes: int = 5 * 1024 * 1024,
                   backup_count: int = 1,
                   log_format: Optional[str] = None,
                   propagate: bool = False) -> logging.Logger:
        """
        获取或创建日志器

        Args:
            name: 日志器名称，None表示获取当前线程的日志器
            log_file: 日志文件路径，None表示不输出到文件
            log_level: 日志级别
            console_output: 是否输出到控制台
            max_bytes: 单个日志文件最大字节数
            backup_count: 备份文件数量
            log_format: 日志格式
            propagate: 是否向上层logger传播

        Returns:
            logging.Logger 实例
        """
        # 如果没有指定名称，返回当前线程的日志器
        if name is None:
            return cls._get_current_logger()

        # 参数验证
        if not isinstance(name, str):
            raise ValueError("logger name must be a string")

        with cls._lock:
            # 检查是否已存在
            if name in cls._loggers:
                return cls._loggers[name]

            logger = logging.getLogger(name)

            # 避免重复添加handler
            if logger.handlers:
                cls._loggers[name] = logger
                return logger

            # 设置日志级别
            log_level_upper = log_level.upper()
            if hasattr(logging, log_level_upper):
                logger.setLevel(getattr(logging, log_level_upper))
            else:
                logger.setLevel(logging.INFO)
                logger.warning(f"无效的日志级别: {log_level}，使用默认级别 INFO")

            # 设置是否向上传播
            logger.propagate = propagate

            # 默认日志格式
            if log_format is None:
                log_format = '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'

            formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')

            # 文件输出
            if log_file:
                try:
                    log_path = Path(log_file)
                    log_path.parent.mkdir(parents=True, exist_ok=True)

                    file_handler = RotatingFileHandler(
                        filename=str(log_path),
                        maxBytes=max_bytes,
                        backupCount=backup_count,
                        encoding='utf-8'
                    )
                    file_handler.setFormatter(formatter)
                    logger.addHandler(file_handler)
                except Exception as e:
                    logger.error(f"创建文件handler失败: {e}")

            # 控制台输出
            if console_output:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

            cls._loggers[name] = logger

            # 注册退出清理
            if not cls._cleanup_registered:
                atexit.register(cls._cleanup)
                cls._cleanup_registered = True

            return logger

    @classmethod
    def set_current_logger(cls, logger: logging.Logger) -> None:
        """设置当前线程的日志器"""
        cls._thread_local.current_logger = logger

    @classmethod
    def get_current_logger(cls) -> Optional[logging.Logger]:
        """获取当前线程已设置的日志器；未设置时返回None，不创建默认日志器"""
        return getattr(cls._thread_local, 'current_logger', None)

    @classmethod
    def _get_current_logger(cls) -> logging.Logger:
        """获取当前线程的日志器"""
        current_logger = cls.get_current_logger()
        if current_logger is not None:
            return current_logger

        # 创建默认日志器
        logger = cls.get_logger("default", console_output=True)
        cls.set_current_logger(logger)
        return logger

    @classmethod
    def clear_current_logger(cls) -> None:
        """清除当前线程的日志器"""
        if hasattr(cls._thread_local, 'current_logger'):
            delattr(cls._thread_local, 'current_logger')

    @classmethod
    def info(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录INFO级别日志"""
        cls._get_current_logger().info(message, *args, **kwargs)

    @classmethod
    def error(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录ERROR级别日志"""
        cls._get_current_logger().error(message, *args, **kwargs)

    @classmethod
    def debug(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录DEBUG级别日志"""
        cls._get_current_logger().debug(message, *args, **kwargs)

    @classmethod
    def warning(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录WARNING级别日志"""
        cls._get_current_logger().warning(message, *args, **kwargs)

    @classmethod
    def critical(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录CRITICAL级别日志"""
        cls._get_current_logger().critical(message, *args, **kwargs)

    @classmethod
    def exception(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录EXCEPTION级别日志（包含异常堆栈）"""
        cls._get_current_logger().exception(message, *args, **kwargs)

    @classmethod
    def log(cls, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        """记录指定级别的日志"""
        cls._get_current_logger().log(level, message, *args, **kwargs)

    @classmethod
    def allure_step(cls, message: str):
        """添加 allure step， 统一入口"""
        try:
            allure.step(message)
        except Exception as e:
            cls.error(f"allure_step() 错误: {e}")

    @classmethod
    def assert_error(cls, message: str, *args: Any, **kwargs: Any) -> None:
        """记录ERROR级别日志, 并报错，结束Case 运行"""
        cls._get_current_logger().error(message, *args, **kwargs)
        raise AssertionError(message)

    @classmethod
    def close_logger(cls, name: str) -> None:
        """关闭指定名称的日志器"""
        with cls._lock:
            if name in cls._loggers:
                logger = cls._loggers[name]
                for handler in logger.handlers[:]:
                    try:
                        handler.close()
                        logger.removeHandler(handler)
                    except Exception:
                        pass
                del cls._loggers[name]

    @classmethod
    def close_all(cls) -> None:
        """关闭所有日志器"""
        for name in list(cls._loggers.keys()):
            cls.close_logger(name)

    @classmethod
    def _cleanup(cls) -> None:
        """清理资源（退出时自动调用）"""
        cls.close_all()

    @classmethod
    def get_logger_names(cls) -> list:
        """获取所有已创建的日志器名称"""
        return list(cls._loggers.keys())

    @classmethod
    def cleanup_old_logs(cls, days: int = 7, log_folder_path: Optional[str] = None) -> int:
        """
        删除指定天数之前的日志文件夹
        
        Args:
            days: 保留天数，默认7天
            log_folder_path: 日志根目录路径，None则使用GlobalVar.LOG_FOLDER_PATH
            
        Returns:
            int: 删除的文件夹数量
        """
        from src.base.const import GlobalVar

        if log_folder_path is None:
            log_folder_path = GlobalVar.LOG_FOLDER_PATH

        log_root = Path(log_folder_path)

        # 检查日志目录是否存在
        if not log_root.exists():
            cls.info(f"日志目录不存在: {log_root}")
            return 0

        # 计算截止日期
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = 0

        cls.info(f"开始清理 {days} 天前的日志文件夹，截止日期: {cutoff_date.strftime('%Y-%m-%d')}")

        # 遍历日志根目录下的所有文件夹
        for folder in log_root.iterdir():
            if folder.is_dir():
                try:
                    # 尝试解析文件夹名为日期格式 YYYYMMDD
                    folder_date_str = folder.name
                    if len(folder_date_str) == 8 and folder_date_str.isdigit():
                        folder_date = datetime.strptime(folder_date_str, '%Y%m%d')

                        # 如果文件夹日期早于截止日期，则删除
                        if folder_date < cutoff_date:
                            cls.info(f"删除过期日志文件夹: {folder.name}")

                            # 递归删除文件夹及其内容
                            import shutil
                            shutil.rmtree(folder)
                            deleted_count += 1

                except (ValueError, OSError) as e:
                    # 如果无法解析日期或删除失败，记录警告但继续处理
                    cls.warning(f"处理日志文件夹 {folder.name} 时出错: {e}")
                    continue

        cls.info(f"日志清理完成，共删除 {deleted_count} 个文件夹")
        return deleted_count
