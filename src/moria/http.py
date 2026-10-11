"""A polite HTTP client: an identifying user agent, a minimum interval per host, retries with backoff that honour
Retry-After, and robots.txt for web pages (design §5, SOP §16.2).

It goes through the environment's proxy settings (httpx trust_env), and never logs query strings, which may carry
API keys.
"""

from __future__ import annotations

import time
import urllib.robotparser
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from .config import HttpConfig

RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """A request that still failed after its retries. The message names the host and path only."""


def _safe(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


class PoliteClient:
    def __init__(self, cfg: HttpConfig, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.cfg = cfg
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._client = httpx.Client(
            headers={"User-Agent": cfg.user_agent},
            timeout=cfg.timeout_s,
            follow_redirects=True,
            transport=transport,
        )
        self.requests = 0

    def close(self) -> None:
        self._client.close()

    def _wait_for_host(self, host: str) -> None:
        interval = self.cfg.host_min_interval_s.get(host, self.cfg.default_min_interval_s)
        last = self._last.get(host)
        if last is not None:
            remaining = interval - (time.monotonic() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = time.monotonic()

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = None  # no robots.txt: allowed
            try:
                resp = self.get(f"{base}/robots.txt", retries=1, ok_statuses=(200, 401, 403, 404, 410))
                if resp.status_code == 200:
                    parser = urllib.robotparser.RobotFileParser()
                    parser.parse(resp.text.splitlines())
            except FetchError:
                parser = None
            self._robots[base] = parser
        parser = self._robots[base]
        return True if parser is None else parser.can_fetch(self.cfg.user_agent, url)

    def get(
        self,
        url: str,
        params: dict | None = None,
        check_robots: bool = False,
        retries: int | None = None,
        ok_statuses: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        if check_robots and not self.allowed_by_robots(url):
            raise FetchError(f"disallowed by robots.txt: {_safe(url)}")
        host = urlsplit(url).netloc
        attempts = (self.cfg.max_retries if retries is None else retries) + 1
        last_error = "no attempt made"
        for attempt in range(attempts):
            self._wait_for_host(host)
            self.requests += 1
            try:
                resp = self._client.get(url, params=params)
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}"
                self._sleep(self.cfg.backoff_s * (2**attempt))
                continue
            if resp.status_code in ok_statuses:
                return resp
            last_error = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUSES:
                break
            self._sleep(self._retry_after(resp) or self.cfg.backoff_s * (2**attempt))
        raise FetchError(f"{last_error} after {attempt + 1} attempt(s): {_safe(url)}")

    @staticmethod
    def _retry_after(resp: httpx.Response) -> float | None:
        value = resp.headers.get("Retry-After")
        if not value:
            return None
        if value.isdigit():
            return min(float(value), 300.0)
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
            return max(0.0, min(delay, 300.0))
        except (TypeError, ValueError):
            return None
