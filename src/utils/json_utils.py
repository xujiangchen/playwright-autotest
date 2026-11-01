import json
from pathlib import Path
from typing import Any, Union, Dict, List, Optional


class JsonUtils:
    """
    JSON工具类，提供静态方法处理常见的JSON操作
    """
    DEFAULT_ENCODING = 'utf-8'

    @staticmethod
    def read_json(file_path: Union[str, Path], encoding: str = None) -> Any:
        """"
        从文件读取JSON数据

        Args:
        file_path: JSON文件路径
        encoding: 文件编码，默认使用DEFAULT_ENCODING

        Returns:
        解析后的JSON数据
        """
        if encoding is None:
            encoding = JsonUtils.DEFAULT_ENCODING
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            with open(file_path, 'r', encoding=encoding) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            raise
        except Exception as e:
            print(f"读取文件失败: {e}")
            raise

    @staticmethod
    def write_json(data: Any, file_path: Union[str, Path],
                   indent: int = 2, ensure_ascii: bool = False,
                   encoding: str = None) -> bool:
        """
        将数据写入JSON文件

        Args:
            data: 要写入的数据
            file_path: 输出文件路径
            indent: 缩进空格数
            ensure_ascii: 是否确保ASCII编码
            encoding: 文件编码，默认使用DEFAULT_ENCODING

        Returns:
            bool: 写入成功返回True
        """
        if encoding is None:
            encoding = JsonUtils.DEFAULT_ENCODING

        try:
            file_path = Path(file_path)
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding=encoding) as f:
                json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            print(f"JSON数据已写入: {file_path}")
            return True
        except Exception as e:
            print(f"写入JSON文件失败: {e}")
            raise

    @staticmethod
    def parse_json_string(json_str: str) -> Any:
        """
        解析JSON字符串

        Args:
            json_str: JSON格式的字符串

        Returns:
            解析后的数据
        """
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON字符串解析错误: {e}")
            raise

    @staticmethod
    def to_json_string(data: Any, indent: Optional[int] = None,
                       ensure_ascii: bool = False) -> str:
        """
        将数据转换为JSON字符串

        Args:
            data: 要转换的数据
            indent: 缩进空格数，None表示不缩进
            ensure_ascii: 是否确保ASCII编码

        Returns:
            JSON格式的字符串
        """
        try:
            return json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        except Exception as e:
            print(f"转换为JSON字符串失败: {e}")
            raise

    @staticmethod
    def validate_json(data: Any) -> bool:
        """
        验证数据是否为有效的JSON格式

        Args:
            data: 要验证的数据

        Returns:
            bool: 是否为有效JSON
        """
        try:
            json.dumps(data)
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def merge_json(json1: Dict, json2: Dict, overwrite: bool = True) -> Dict:
        """
        合并两个JSON对象

        Args:
            json1: 第一个JSON对象
            json2: 第二个JSON对象
            overwrite: 是否覆盖重复键，True则用json2的值覆盖，False则保留原值

        Returns:
            合并后的JSON对象
        """
        result = json1.copy()

        def _deep_merge(dict1, dict2, overwrite):
            for key, value in dict2.items():
                if key in dict1:
                    if isinstance(dict1[key], dict) and isinstance(value, dict):
                        # 递归合并嵌套的字典
                        _deep_merge(dict1[key], value, overwrite)
                    elif overwrite:
                        dict1[key] = value
                else:
                    dict1[key] = value
            return dict1

        return _deep_merge(result, json2, overwrite)

    @staticmethod
    def extract_values(data: Any, key_path: str, separator: str = '.') -> List[Any]:
        """
        根据键路径提取JSON中的值

        Args:
            data: JSON数据
            key_path: 键路径，如 "user.address.city"
            separator: 路径分隔符

        Returns:
            匹配到的值列表
        """
        keys = key_path.split(separator)
        results = []

        def _extract(obj, current_keys):
            if not current_keys:
                results.append(obj)
                return

            current_key = current_keys[0]
            remaining_keys = current_keys[1:]

            if isinstance(obj, dict):
                if current_key in obj:
                    _extract(obj[current_key], remaining_keys)
                else:
                    # 键不存在时，尝试在所有值中递归查找
                    for value in obj.values():
                        _extract(value, keys)
            elif isinstance(obj, list):
                for item in obj:
                    _extract(item, keys)

        _extract(data, keys)
        return results

    @staticmethod
    def update_value(data: Any, key_path: str, new_value: Any,
                     separator: str = '.') -> bool:
        """
        更新JSON中指定路径的值

        Args:
            data: JSON数据
            key_path: 键路径
            new_value: 新值
            separator: 路径分隔符

        Returns:
            bool: 更新成功返回True
        """
        keys = key_path.split(separator)
        current = data

        try:
            # 遍历到倒数第二个键
            for key in keys[:-1]:
                if isinstance(current, dict):
                    if key not in current:
                        return False
                    current = current[key]
                elif isinstance(current, list) and key.isdigit():
                    idx = int(key)
                    if idx >= len(current):
                        return False
                    current = current[idx]
                else:
                    return False

            # 更新最后一个键的值
            last_key = keys[-1]
            if isinstance(current, dict):
                current[last_key] = new_value
                return True
            elif isinstance(current, list) and last_key.isdigit():
                idx = int(last_key)
                if idx >= len(current):
                    return False
                current[idx] = new_value
                return True
            else:
                return False

        except (KeyError, IndexError, ValueError):
            return False
