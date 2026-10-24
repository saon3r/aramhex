"""测试专用本地传输：只给显式注入的测试用，生产代码没有 allow_local 之类的开关。

真实请求 127.0.0.1 上指定的端口；路径必须和真实统计数据目录形状一致
（patches/<版本>/<模式>/…），不再接受任意路径。不跟随重定向、不保存 Cookie，
请求头规则和默认传输一样严。
"""

from __future__ import annotations

from urllib.parse import urlsplit

import requests

from lolhex.data import http


class LocalTransport:
    """127.0.0.1:<端口> 的本地 HTTP 传输；可以同时给多个本地来源（坏镜像测试用）。"""

    def __init__(self, *base_urls: str):
        if not base_urls:
            raise ValueError("LocalTransport 至少需要一个本地来源")
        self.origins: set[str] = set()
        for base_url in base_urls:
            p = urlsplit(base_url)
            if (p.scheme != "http" or p.hostname != "127.0.0.1" or not p.port
                    or p.path not in ("", "/") or p.query or p.fragment
                    or p.username is not None or p.password is not None):
                raise ValueError("LocalTransport 只接受 http://127.0.0.1:<端口>")
            self.origins.add(f"http://127.0.0.1:{p.port}")

    def _check(self, url: str) -> None:
        p = urlsplit(url)
        origin = f"{p.scheme}://{p.hostname}:{p.port}" if p.port else ""
        if (origin not in self.origins or p.username is not None or p.password is not None
                or p.query or p.fragment or "%" in url or "\\" in url
                or any(seg in (".", "..") for seg in p.path.split("/"))):
            raise http.PolicyError(f"本地测试传输不允许：{url}")
        if not p.path.startswith("/") or p.path.startswith("//"):
            raise http.PolicyError(f"本地测试传输不允许：{url}")
        if not http._dataset_path_ok(p.path[1:]):
            raise http.PolicyError(f"本地测试传输只接受真实统计数据路径：{url}")

    @staticmethod
    def _session(headers):
        s = requests.Session()
        s.trust_env = False
        s.headers.update(http._request_headers(headers))
        return s

    def get(self, url: str, *, timeout: float = 20, headers: dict | None = None):
        hdrs = http._request_headers(headers)
        self._check(url)
        with self._session(hdrs) as s:
            r = s.get(url, timeout=timeout, allow_redirects=False)
        http._reject_redirect(r, url)
        return r

    def fetch(self, url: str, *, timeout: float = 30, headers: dict | None = None,
              on_bytes=None) -> bytes:
        hdrs = http._request_headers(headers)
        self._check(url)
        with self._session(hdrs) as s:
            with s.get(url, timeout=timeout, stream=True, allow_redirects=False) as r:
                http._reject_redirect(r, url)
                r.raise_for_status()
                chunks = []
                for chunk in r.iter_content(64 * 1024):
                    chunks.append(chunk)
                    if on_bytes:
                        on_bytes(len(chunk))
                return b"".join(chunks)
