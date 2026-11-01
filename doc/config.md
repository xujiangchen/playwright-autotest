# 配置模块：`Config` 与 `ConfigManager`

本文介绍 `src/base/config_v2.py` 中的两个核心类：`ConfigManager` 负责读取和检查配置，`Config` 保存一次运行使用的只读配置快照。

## 整体流程

```text
ConfigManager.load()
        ↓
读取并检查 JSON 配置
        ↓
_build_snapshot() 创建快照
        ↓
返回 Config 对象
```

`load()` 只在内存中创建快照，不会修改或保存配置文件。需要保存时，再调用 `write_snapshot()`。

## `Config`：一次运行的配置快照

### `@dataclass(frozen=True)`

`dataclasses` 是 Python 自带的标准库。`@dataclass` 会自动生成初始化等常用方法，减少数据类的样板代码。

`frozen=True` 表示对象创建后不能重新给字段赋值，适合表示不希望被修改的数据。用途上类似 Java `record`。

```python
@dataclass(frozen=True)
class Config:
    environment: str
    browser_type: str
```

要区分“字段不能重新赋值”和“字段里的内容不能修改”：

- 字符串本身不可变；`frozen=True` 还会阻止把字段换成另一个字符串，例如 `config.environment = "PRO"`。
- 如果字段里是列表，单独使用 `frozen=True` 仍允许修改列表内容，例如 `config.items.append("new")`。

因此，本项目还会用 `_freeze()` 递归冻结配置数据：字典转换为只读映射，列表转换为元组；嵌套的字典和列表也会继续转换。两者配合后，既不能重新给 `Config` 字段赋值，也不能通过字段里的嵌套容器修改快照。
- 字典 → 只读映射（MappingProxyType）
- 列表 → 元组

### `@property`：像属性一样读取

`@property` 让方法可以像属性一样读取。配置值要通过实例获取，例如 `config.ENV`；直接写 `Config.ENV` 不会得到某次运行的配置值。

- `config.ENV` 是 `config.environment` 的兼容名称。
- `config.BROWSER_TYPE` 是 `config.browser_type` 的兼容名称。
- `config.BASE_URL` 根据当前环境，从网址配置中查出对应网址。

### `to_dict()`：获取可修改副本

`config.to_dict()` 返回完整配置数据的一份可修改副本，包括配置文件中的扩展字段。副本中也包含本次加载时应用的环境、浏览器覆盖值。

```python
data = config.to_dict()
data["GENERAL"]["ENV"] = "PRO"

print(data["GENERAL"]["ENV"])  # PRO
print(config.ENV)               # 原快照仍是 DEV
```

修改副本不会改变 `Config` 快照，也不会自动写回配置文件。需要普通字典用于序列化或单独修改时，再调用 `to_dict()`。

## `ConfigManager`：读取、检查和保存配置

### 初始化与读取路径

```python
manager = ConfigManager()
```

不传路径时使用项目默认配置文件；也可以指定路径：

```python
manager = ConfigManager(config_path="configs/conf.json")
```

初始化只保存路径，不会立即读取文件。这个路径表示 `load()` **从哪里读取配置**。

### `load()`：读取配置并创建快照

```python
config = manager.load(env="DEV", browser_type="chrome")
```

`load()` 读取并解析 JSON，然后把配置数据交给 `_build_snapshot()` 检查并创建 `Config`。传入的环境和浏览器值只应用到内存快照，不会写回来源文件。

### `write_snapshot()`：把快照保存到文件

```python
manager.write_snapshot(config, "runtime-configs/build-123/conf.json")
```

`write_snapshot()` 的路径表示快照**写到哪里**，与初始化时的读取路径是两个概念。并发构建时，每个构建应使用自己的输出路径，避免互相覆盖。

## 初始化脚本与 pytest 分开运行时

如果初始化脚本和 pytest 是两条独立命令，它们通常运行在不同进程中。初始化进程结束后，内存中的 `Config` 对象不能直接交给 pytest，因此要先保存快照，再让 pytest 从同一路径读取：

```python
# 初始化脚本
config = manager.load(env="DEV")
manager.write_snapshot(config, snapshot_path)

# pytest 启动时
config = ConfigManager(config_path=snapshot_path).load()
```

两个进程必须使用同一个快照路径。当前 `init_env.py` 已使用 V2 管理器写入构建专属快照；**pytest 仍在使用旧的 `src/base/config.py`，不会自动读取该快照。** 要让测试使用快照，还需要让 pytest 的配置入口从该路径加载。
