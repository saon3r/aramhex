"""公开数据源的 HTTP 边界：只发允许的匿名 HTTPS GET，带超时、重试、限速。

所有联网请求都经过这里。默认传输只放行三处统计数据、DataDragon 静态资料和
CommunityDragon 英文海克斯字典的固定地址；其余地址在发出请求之前就拒绝。
不读取游戏内存，也不使用安装编号、Cookie 或账号信息。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from urllib.parse import urlsplit

import requests

from .. import __version__, _CA

# 稳定的程序版本 User-Agent；不接受调用方自定义，也不发 Referer。
APP_UA = f"aramhex/{__version__}"
_ALLOWED_HEADERS = frozenset({"user-agent", "accept"})
_ALLOWED_ACCEPT = frozenset({"*/*", "application/json"})

_lock = threading.Lock()
_last_request = 0.0
# 两次请求之间至少间隔多少秒；所有数据源共用，保证低频。
MIN_INTERVAL = 0.35


class FetchError(RuntimeError):
    pass


class PolicyError(FetchError):
    """请求不在放行范围内：在发出任何网络请求之前抛出。"""


# 统计数据文件和路径模板（真实仓库形状）：patches/<版本>/<模式>[/bands/<分段>]/<名字>.json，
# 或 patches/<版本>/<模式>.pack.xz。没有 mode 目录的形状从来没有存在过。
_DATASET_JSON = r"[0-9A-Za-z][0-9A-Za-z_-]*\.json"
_PATCH = r"[0-9A-Za-z][0-9A-Za-z._-]*"
_MODE = r"[0-9A-Za-z][0-9A-Za-z_-]*"
_DATASET_PATH = re.compile(
    rf"(?:latest\.json"
    rf"|patches/{_PATCH}/{_MODE}\.pack\.xz"
    rf"|patches/{_PATCH}/{_MODE}/(?:{_DATASET_JSON}|bands/(?:casual|mid|high|top)/{_DATASET_JSON}))\Z"
)
# DataDragon：版本号模板固定，只放行 champion/item 的元数据和图标。
_VERSION = r"[0-9]+(?:\.[0-9]+)*"
_DDRAGON_PATHS = (
    re.compile(r"/api/versions\.json\Z"),
    re.compile(rf"/cdn/{_VERSION}/data/(?:en_GB|en_US)/(?:champion|item)\.json\Z"),
    re.compile(rf"/cdn/{_VERSION}/img/champion/[A-Za-z0-9]+\.png\Z"),
    re.compile(rf"/cdn/{_VERSION}/img/item/[0-9]+\.png\Z"),
)
# CommunityDragon：只放行英文（默认）静态海克斯字典，别的资源不放行。
_CDRAGON_AUGMENTS = "/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json"
# 统计数据两个来源：官网镜像在前，raw GitHub 兜底。
_STATS_PREFIXES = {
    "aramhex.com": "/u/data/",
    "raw.githubusercontent.com": "/czgreat/aramhex-data/main/",
}
_ALLOWED_HOSTS = frozenset(_STATS_PREFIXES) | {"ddragon.leagueoflegends.com",
                                               "raw.communitydragon.org"}


def _throttle() -> None:
    global _last_request
    with _lock:
        wait = _last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _request_headers(headers: dict | None) -> dict[str, str]:
    """校验并补全请求头：User-Agent 固定为程序版本号，Accept 只允许固定常量，不发 Referer。"""
    out: dict[str, str] = {}
    seen: set[str] = set()
    for name, value in dict(headers or {}).items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise PolicyError("请求头必须是字符串")
        low = name.lower()
        if name != name.strip() or low not in _ALLOWED_HEADERS or any(c in name for c in "\r\n:"):
            raise PolicyError(f"不允许的请求头：{name}")
        if low in seen:
            raise PolicyError(f"重复的请求头：{name}")
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
            raise PolicyError(f"请求头里有控制字符：{name}")
        if low == "user-agent" and value != APP_UA:
            raise PolicyError("User-Agent 必须是程序版本号")
        if low == "accept" and value not in _ALLOWED_ACCEPT:
            raise PolicyError(f"不允许的 Accept：{value}")
        seen.add(low)
        out[name] = value
    if "user-agent" not in seen:
        out["User-Agent"] = APP_UA
    return out


def _ca_bundle() -> str:
    """沿用程序内的根证书包，同时尊重用户显式设置的 CA 环境变量；绝不关闭校验。"""
    return os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE") or str(_CA)


def _new_session(headers: dict[str, str]) -> requests.Session:
    """每次请求一个独立会话：不读环境代理/netrc，不保存 Cookie，CA 校验保持开启。"""
    s = requests.Session()
    s.trust_env = False
    s.verify = _ca_bundle()
    s.headers.update(headers)
    return s


def _dataset_path_ok(path: str) -> bool:
    """统计数据相对路径是否落在允许的文件模板里。"""
    return bool(_DATASET_PATH.fullmatch(path))


def authorize(url: str, *, method: str = "GET", headers: dict | None = None):
    """检查一次请求是否放行，不发送任何东西；放行时返回 urlsplit 结果。"""
    if method != "GET":
        raise PolicyError(f"只允许 GET：{method}")
    if not isinstance(url, str) or not url or not url.isascii():
        raise PolicyError("地址不合法")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise PolicyError("地址里有空白或控制字符")
    if "%" in url:
        raise PolicyError("不允许百分号编码")
    if "\\" in url:
        raise PolicyError("不允许反斜杠")
    if headers:
        _request_headers(headers)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise PolicyError(f"地址不合法：{e}") from e
    if parts.scheme != "https":
        raise PolicyError("只允许 HTTPS")
    if parts.username is not None or parts.password is not None:
        raise PolicyError("不允许用户信息")
    if port is not None and port != 443:
        raise PolicyError(f"不允许端口 {port}")
    if parts.query or parts.fragment:
        raise PolicyError("不允许查询串或片段")
    if any(seg in (".", "..") for seg in parts.path.split("/")):
        raise PolicyError("不允许路径穿越")
    host = parts.hostname or ""
    if host not in _ALLOWED_HOSTS:
        raise PolicyError(f"不允许的地址：{host or url}")
    if host in _STATS_PREFIXES:
        prefix = _STATS_PREFIXES[host]
        if not parts.path.startswith(prefix):
            raise PolicyError(f"统计数据只允许 {prefix} 下的文件")
        if not _dataset_path_ok(parts.path[len(prefix):]):
            raise PolicyError(f"不允许的统计数据文件：{parts.path}")
    elif host == "ddragon.leagueoflegends.com":
        if not any(p.fullmatch(parts.path) for p in _DDRAGON_PATHS):
            raise PolicyError(f"不允许的 DataDragon 路径：{parts.path}")
    elif parts.path != _CDRAGON_AUGMENTS:
        raise PolicyError(f"不允许的 CommunityDragon 路径：{parts.path}")
    return parts


def _reject_redirect(r: requests.Response, url: str) -> None:
    """3xx 一律拒绝，绝不跟到 Location 上的别的地址。"""
    if 300 <= r.status_code < 400:
        raise PolicyError(f"不跟随重定向：HTTP {r.status_code} {url}")


class Transport:
    """默认传输：策略先于发送，不跟随重定向，每次请求独立（不保存、不回放 Cookie）。"""

    def get(self, url: str, *, timeout: float = 20,
            headers: dict | None = None) -> requests.Response:
        hdrs = _request_headers(headers)
        authorize(url)
        _throttle()
        with _new_session(hdrs) as s:
            r = s.get(url, timeout=timeout, allow_redirects=False)
        _reject_redirect(r, url)
        return r

    def fetch(self, url: str, *, timeout: float = 30, headers: dict | None = None,
              on_bytes=None) -> bytes:
        hdrs = _request_headers(headers)
        authorize(url)
        _throttle()
        with _new_session(hdrs) as s:
            with s.get(url, timeout=timeout, stream=True, allow_redirects=False) as r:
                _reject_redirect(r, url)
                r.raise_for_status()
                chunks = []
                for chunk in r.iter_content(64 * 1024):
                    chunks.append(chunk)
                    if on_bytes:
                        on_bytes(len(chunk))
                return b"".join(chunks)


DEFAULT_TRANSPORT = Transport()


def get(url: str, *, timeout: float = 20, retries: int = 2, headers: dict | None = None,
        referer: str | None = None, transport=None) -> requests.Response:
    # 直到 Task 4B 删掉 tencent.py 的旧调用为止保留 kwarg，但任何 Referer 都直接拒绝。
    if referer:
        raise PolicyError("不再允许 Referer")
    hdrs = dict(headers or {})
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            t = DEFAULT_TRANSPORT if transport is None else transport
            r = t.get(url, timeout=timeout, headers=hdrs or None)
            if r.status_code == 200:
                return r
            last = FetchError(f"HTTP {r.status_code} {url}")
            if r.status_code in (403, 404):
                break
        except PolicyError:
            raise
        except requests.RequestException as e:  # 连接错误、超时
            last = e
        time.sleep(0.8 * (attempt + 1))
    raise FetchError(str(last))


def get_json(url: str, *, transport=None, **kw):
    r = get(url, transport=transport, **kw)
    # 腾讯部分 .js 文件本身就是 JSON；统一用 utf-8 解。
    return json.loads(r.content.decode("utf-8-sig"))


def fetch(url: str, *, timeout: float = 30, headers: dict | None = None, on_bytes=None,
          transport=None) -> bytes:
    """边下边报进度的下载（更新文件、统计数据用）：每收到一块就调 on_bytes(这一块的字节数)。"""
    t = DEFAULT_TRANSPORT if transport is None else transport
    return t.fetch(url, timeout=timeout, headers=headers, on_bytes=on_bytes)
