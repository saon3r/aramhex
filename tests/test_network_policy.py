"""网络边界：默认传输在发出请求之前校验地址、方法和请求头，只放行固定 HTTPS GET。

拒绝用例一律证明没有发出请求；成功响应用假传输只测策略边界，真实 HTTP 用 LocalTransport。
真实统计数据路径从随程序发布的清单里取，避免用虚构的目录形状把策略测成绿的。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests.sessions as requests_sessions

import lolhex
from httpfixtures import LocalTransport
from lolhex.data import http, public
from lolhex.data.public import DATA_SOURCES

STATS = "https://aramhex.com/u/data/latest.json"

ALLOWED = [
    STATS,
    "https://aramhex.com/u/data/patches/16.21/normal.pack.xz",
    "https://aramhex.com/u/data/patches/16.21/normal/heroes.json",
    "https://aramhex.com/u/data/patches/16.21/normal/bands/mid/hero_augments.json",
    "https://aramhex.com/u/data/patches/16.20-pbe/first-prismatic/heroes.json",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/latest.json",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/patches/16.21/normal/heroes.json",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/patches/16.21/normal.pack.xz",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/patches/16.21/normal/bands/high/hero_augments.json",
    "https://ddragon.leagueoflegends.com/api/versions.json",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_GB/champion.json",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_US/item.json",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/champion/Ahri.png",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/item/1001.png",
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json",
]

DENIED = [
    # 协议、端口、身份信息
    "http://aramhex.com/u/data/latest.json",
    "https://aramhex.com:8443/u/data/latest.json",
    "https://aramhex.com:444/u/data/latest.json",
    "https://user@aramhex.com/u/data/latest.json",
    "https://user:pw@aramhex.com/u/data/latest.json",
    "https://aramhex.com@evil.example/u/data/latest.json",
    # 主机前缀 / 后缀攻击
    "https://aramhex.com.evil.example/u/data/latest.json",
    "https://notaramhex.com/u/data/latest.json",
    "https://raw.githubusercontent.com.evil.example/czgreat/aramhex-data/main/latest.json",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/../../etc/passwd",
    "https://raw.githubusercontent.com/someone/aramhex-data/main/latest.json",
    # 路径穿越（原样、百分号、双重编码、反斜杠）
    "https://aramhex.com/u/data/../secret.json",
    "https://aramhex.com/u/data/%2e%2e/secret.json",
    "https://aramhex.com/u/data/%252e%252e/secret.json",
    "https://aramhex.com/u/data/patches/16.21/normal/..%5cheroes.json",
    "https://aramhex.com/u/data/patches/16.21\\..\\heroes.json",
    "https://aramhex.com/u/data/patches/16.21/normal/../evil.json",
    "https://aramhex.com/u/data/patches/16.21/na.mer/heroes.json",
    # 查询串、片段、任意路径
    "https://aramhex.com/u/data/latest.json?x=1",
    "https://aramhex.com/u/data/latest.json#x",
    "https://aramhex.com/u/data/latest.json/",
    "https://aramhex.com/u/other/latest.json",
    "https://aramhex.com/u/data/patches/16.21/normal/heroes.exe",
    "https://aramhex.com/u/data/patches/16.21/normal/sub/evil.json",
    "https://aramhex.com/u/data/patches/16.21/normal/heroes.json/extra",
    # 没有 mode 目录的旧形状：真实数据从来不是这样
    "https://aramhex.com/u/data/patches/16.21.pack.xz",
    "https://aramhex.com/u/data/patches/16.21/heroes.json",
    "https://aramhex.com/u/data/patches/16.21/bands/mid/hero_augments.json",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/patches/16.21.pack.xz",
    "https://raw.githubusercontent.com/czgreat/aramhex-data/main/patches/16.21/heroes.json",
    # DataDragon：别的数据类型、任意 cdn
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_US/summoner.json",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_US/spell.json",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/img/spell/SummonerFlash.png",
    "https://ddragon.leagueoflegends.com/cdn/16.21.1/plugins/evil.js",
    "https://ddragon.leagueoflegends.com/api/versions.json?x=1",
    # CommunityDragon：只放行英文静态海克斯字典
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/zh_cn/v1/cherry-augments.json",
    "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/other.json",
    # 腾讯、自更新、云控等旧来源
    "https://game.gtimg.cn/images/lol/act/img/js/items/items.js",
    "https://game.gtimg.cn/images/lol/act/img/champion/Ahri.png",
    "https://mlol.qt.qq.com/go/database/versionlist?zone=lol",
    "https://cloud.example.com/report",
]


class _Response:
    status_code = 200
    content = b"{}"
    headers: dict = {}


def _record_send(monkeypatch, response=None):
    """拦截真正的 Session.send：拒绝用例证明它没被调用，策略用例可检查 prepared 请求。"""
    sent = []

    def fake_send(self, request, **kwargs):
        sent.append((self, request, kwargs))
        return response or _Response()

    monkeypatch.setattr(requests_sessions.Session, "send", fake_send)
    return sent


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed_urls_pass_policy(url):
    assert http.authorize(url).hostname


@pytest.mark.parametrize("url", DENIED)
def test_denied_urls_are_rejected_before_sending(url, monkeypatch):
    sent = _record_send(monkeypatch)
    with pytest.raises(http.PolicyError):
        http.get(url)
    assert sent == []


@pytest.mark.parametrize("base", DATA_SOURCES)
def test_real_bundled_manifest_paths_are_authorized(base):
    """C1 回归：用随程序发布的真实清单推导 pack 和每个文件，两个来源都必须放行。"""
    manifest = json.loads((public.BUNDLED_DIR / "latest.json").read_text(encoding="utf-8"))
    path = manifest["path"]
    assert path.startswith("patches/") and path.count("/") == 2, path  # patches/<patch>/<mode>
    http.authorize(f"{base}/latest.json")
    http.authorize(f"{base}/{path}.pack.xz")
    assert manifest["files"]
    for name in manifest["files"]:
        assert http._dataset_path_ok(f"{path}/{name}")
        http.authorize(f"{base}/{path}/{name}")
    assert http._dataset_path_ok(f"{path}/bands/casual/heroes.json")
    assert not http._dataset_path_ok("patches/16.21/heroes.json")
    assert not http._dataset_path_ok("patches/16.21.pack.xz")


def test_configured_stats_sources_are_the_two_allowlisted_ones():
    assert DATA_SOURCES == ["https://aramhex.com/u/data",
                            "https://raw.githubusercontent.com/czgreat/aramhex-data/main"]


def test_only_get_is_allowed():
    with pytest.raises(http.PolicyError):
        http.authorize(STATS, method="POST")
    with pytest.raises(http.PolicyError):
        http.authorize(STATS, method="HEAD")


BAD_HEADERS = [
    {"Cookie": "id=1"},
    {"cookie": "id=1"},
    {"Authorization": "Bearer x"},
    {"Proxy-Authorization": "Basic x"},
    {"X-Api-Key": "x"},
    {"X-Aramhex-Id": "0123456789abcdef"},
    {"Referer": "https://101.qq.com/"},
    {"User-Agent": "Mozilla/5.0"},
    {"user-agent": "riot#1234"},
    {"Accept": "text/html"},
    {"Accept": "application/json;q=1"},
    {"User-Agent": http.APP_UA + "\r\nCookie: a=b"},
    {"User-Agent": 1},
    {"User-Agent ": http.APP_UA},
]


@pytest.mark.parametrize("headers", BAD_HEADERS)
def test_remote_identity_and_custom_headers_are_denied_before_sending(headers, monkeypatch):
    sent = _record_send(monkeypatch)
    with pytest.raises(http.PolicyError):
        http.get(STATS, headers=headers)
    assert sent == []


def test_referer_kwarg_is_rejected_until_its_caller_is_gone(monkeypatch):
    sent = _record_send(monkeypatch)
    with pytest.raises(http.PolicyError):
        http.get(STATS, referer="https://101.qq.com/")
    assert sent == []


def test_default_user_agent_is_the_fixed_app_version():
    assert http._request_headers(None) == {"User-Agent": http.APP_UA}
    assert http._request_headers({"Accept": "*/*"}) == {"Accept": "*/*", "User-Agent": http.APP_UA}
    assert http._request_headers({"user-agent": http.APP_UA}) == {"user-agent": http.APP_UA}
    assert http._request_headers({"Accept": "application/json"})["User-Agent"] == http.APP_UA


def test_public_headers_use_the_boundary_user_agent():
    assert public.headers() == {"User-Agent": http.APP_UA}


def test_default_transport_is_resolved_at_call_time(monkeypatch):
    calls = []

    class FakeTransport:
        def get(self, url, *, timeout=20, headers=None):
            calls.append((url, timeout, headers))
            return _Response()

    monkeypatch.setattr(http, "DEFAULT_TRANSPORT", FakeTransport())
    assert http.get(STATS).status_code == 200
    assert http.get_json(STATS) == {}
    assert calls == [(STATS, 20, None), (STATS, 20, None)]


def test_fetch_delegates_to_transport(monkeypatch):
    calls = []

    class FakeTransport:
        def fetch(self, url, *, timeout=30, headers=None, on_bytes=None):
            calls.append((url, timeout, headers))
            if on_bytes:
                on_bytes(3)
            return b"abc"

    monkeypatch.setattr(http, "DEFAULT_TRANSPORT", FakeTransport())
    got = []
    assert http.fetch(STATS, timeout=7, headers={"Accept": "*/*"}, on_bytes=got.append) == b"abc"
    assert calls == [(STATS, 7, {"Accept": "*/*"})]
    assert got == [3]


class _Redirect:
    status_code = 302
    headers = {"Location": "https://evil.example/collect"}


def test_redirect_response_is_rejected_not_followed(monkeypatch):
    sent = _record_send(monkeypatch, response=_Redirect())

    with pytest.raises(http.PolicyError):
        http.get(STATS)
    assert len(sent) == 1 and sent[0][2]["allow_redirects"] is False
    assert sent[0][1].url == STATS  # 没有请求 Location 上的 evil.example


def test_transport_ignores_netrc_and_proxy_environment(monkeypatch):
    """I1：环境里的 netrc/代理不能变成 Authorization、Proxy-Authorization 或改道。"""
    monkeypatch.setenv("HTTPS_PROXY", "http://user:pw@proxy.invalid:3128")
    monkeypatch.setenv("HTTP_PROXY", "http://user:pw@proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)
    monkeypatch.setattr(requests_sessions, "get_netrc_auth", lambda *a, **k: ("u", "p"))
    sent = _record_send(monkeypatch)

    assert http.get(STATS).status_code == 200
    session, request, kwargs = sent[0]
    assert session.trust_env is False and dict(session.proxies) == {}
    assert session.verify == str(lolhex._CA)
    assert len(session.cookies) == 0
    for name in ("Authorization", "Proxy-Authorization", "Cookie"):
        assert name not in request.headers
    assert request.url == STATS


def test_transport_keeps_explicit_ca_override(monkeypatch):
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "C:/custom/ca.pem")
    sent = _record_send(monkeypatch)
    assert http.get(STATS).status_code == 200
    assert sent[0][0].verify == "C:/custom/ca.pem"


@pytest.fixture
def cookie_server():
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append({k.lower(): v for k, v in self.headers.items()})
            self.send_response(200)
            self.send_header("Set-Cookie", "sid=secret; Path=/")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", seen
    httpd.shutdown()


def test_server_cookie_is_not_replayed(cookie_server):
    base, seen = cookie_server
    t = LocalTransport(base)
    assert http.fetch(base + "/latest.json", transport=t) == b"ok"
    assert t.get(base + "/patches/16.21/normal.pack.xz").status_code == 200
    assert len(seen) == 2
    assert all("cookie" not in h for h in seen)
    assert all(h["user-agent"] == http.APP_UA for h in seen)


def test_local_transport_keeps_policy_rules():
    t = LocalTransport("http://127.0.0.1:1")
    with pytest.raises(http.PolicyError):
        t.get("http://127.0.0.1:1/latest.json", headers={"Cookie": "a=b"})
    with pytest.raises(http.PolicyError):
        t.get("http://127.0.0.1:2/latest.json")                    # 不是注入的端口
    with pytest.raises(http.PolicyError):
        t.get("http://127.0.0.1:1/..%2fetc/passwd")                # 编码穿越
    with pytest.raises(http.PolicyError):
        t.get("https://aramhex.com/u/data/latest.json")            # 不是本地来源
    with pytest.raises(http.PolicyError):
        t.get("http://127.0.0.1:1/patches/16.21/heroes.json")      # 没有 mode 目录
    assert http._dataset_path_ok("patches/16.21/normal/heroes.json")


def test_local_transport_rejects_redirect_without_following():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with pytest.raises(http.PolicyError):
            http.fetch(base + "/latest.json", transport=LocalTransport(base))
        assert seen == ["/latest.json"]
    finally:
        httpd.shutdown()
