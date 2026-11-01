"""启动或发现可通过 CDP 接管的本机 Chrome/Edge。"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from src.base.const import GlobalVar


DEBUG_CONFIG_PATH = Path(GlobalVar.PROJECT_BASE_PATH) / "configs" / "debug.json"
DEBUG_PROFILE_PATH = Path(GlobalVar.PROJECT_BASE_PATH) / ".debug-browser-profile"
_HTTP = build_opener(ProxyHandler({}))


def load_debug_config(path: Path = DEBUG_CONFIG_PATH) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"调试配置必须是 JSON 对象: {path}")
    for name in ("enabled", "browser_started"):
        if type(data.get(name)) is not bool:
            raise ValueError(f"调试配置 {name} 必须是布尔值: {path}")
    port = data.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError(f"调试配置 port 必须是 1-65535 的整数: {path}")
    return data


def _save_started(path: Path, data: dict, started: bool) -> None:
    if data["browser_started"] == started:
        return
    updated = {**data, "browser_started": started}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".debug-",
            suffix=".json", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(updated, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    data["browser_started"] = started


def _cdp_info(port: int) -> dict | None:
    try:
        with _HTTP.open(f"http://127.0.0.1:{port}/json/version", timeout=0.5) as response:
            data = json.load(response)
        if (isinstance(data, dict)
                and isinstance(data.get("Browser"), str)
                and isinstance(data.get("webSocketDebuggerUrl"), str)
                and data["webSocketDebuggerUrl"].startswith("ws://")):
            return data
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        pass
    return None


def _port_in_use(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _browser_executable(browser_type: str) -> str:
    if browser_type == "chrome":
        names = ("chrome.exe", "chrome", "google-chrome", "google-chrome-stable")
        relative = ("Google/Chrome/Application/chrome.exe",)
    elif browser_type == "edge":
        names = ("msedge.exe", "msedge", "microsoft-edge")
        relative = ("Microsoft/Edge/Application/msedge.exe",)
    else:
        raise ValueError("CDP 调试模式仅支持 BROWSER_TYPE=chrome 或 edge")

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for root in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")):
        if root:
            for part in relative:
                candidate = Path(root) / part
                if candidate.is_file():
                    return str(candidate)
    raise FileNotFoundError(f"找不到 {browser_type} 可执行文件，请安装浏览器或将其加入 PATH")


def ensure_debug_browser(browser_type: str, config_path: Path = DEBUG_CONFIG_PATH) -> int:
    """确认 CDP 服务可用，必要时启动独立 profile 的浏览器。"""
    if browser_type not in ("chrome", "edge"):
        raise ValueError("CDP 调试模式仅支持 BROWSER_TYPE=chrome 或 edge")
    data = load_debug_config(config_path)
    if not data["enabled"]:
        raise ValueError("debug 模式未开启")
    port = data["port"]
    info = _cdp_info(port)
    if info is not None:
        _save_started(config_path, data, True)
        return port

    _save_started(config_path, data, False)
    if _port_in_use(port):
        raise RuntimeError(f"端口 {port} 已被占用，但未提供可用的 CDP 服务")

    executable = _browser_executable(browser_type)
    profile = DEBUG_PROFILE_PATH if config_path == DEBUG_CONFIG_PATH else config_path.parent / ".debug-browser-profile"
    profile.mkdir(parents=True, exist_ok=True)
    flags = 0
    popen_options = {}
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    process = subprocess.Popen(
        [executable, f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
         f"--user-data-dir={profile}", "--no-first-run"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=flags, **popen_options,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if _cdp_info(port) is not None:
            _save_started(config_path, data, True)
            return port
        if process.poll() is not None:
            raise RuntimeError(f"{browser_type} 已退出，无法在端口 {port} 启动调试服务")
        time.sleep(0.2)
    raise TimeoutError(f"等待 {browser_type} 的 CDP 端口 {port} 就绪超时")
