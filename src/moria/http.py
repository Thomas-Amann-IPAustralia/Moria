"""A polite HTTP client: an identifying user agent, a minimum interval per host, retries with backoff that honour
Retry-After, and robots.txt for web pages (design §5, SOP §16.2).

It goes through the environment's proxy settings (httpx trust_env), and never logs query strings, which may carry
API keys. Every attempt is logged with its host and path, status and time taken, and so is every wait before a retry,
so a slow run shows what it is doing.
"""

from __future__ import annotations

import hashlib
import logging
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config import HttpConfig
from .robots import RobotsRules

RETRY_STATUSES = {429, 500, 502, 503, 504}

log = logging.getLogger("moria.http")


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
        self._robots: dict[str, RobotsRules | None] = {}
        self._client = httpx.Client(
            headers={"User-Agent": cfg.user_agent},
            timeout=cfg.timeout_s,
            follow_redirects=True,
            transport=transport,
        )
        self.requests = 0
        self.outcomes: dict[str, int] = {}  # e.g. {"http_200": 40, "http_429": 3, "error_ReadTimeout": 1}

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
            parser: RobotsRules | None = None  # no robots.txt: allowed
            try:
                resp = self.get(f"{base}/robots.txt", retries=1, ok_statuses=(200, 401, 403, 404, 410))
                if resp.status_code == 200:
                    parser = RobotsRules(resp.text, self.cfg.user_agent)
            except FetchError:
                parser = None
            self._robots[base] = parser
        parser = self._robots[base]
        return True if parser is None else parser.allowed(url)

    def get(
        self,
        url: str,
        params: dict | None = None,
        check_robots: bool = False,
        retries: int | None = None,
        ok_statuses: tuple[int, ...] = (200,),
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """GET with politeness and retries. `headers` carry credentials (never logged), so keys stay out of URLs."""
        return self.request(
            "GET",
            url,
            params=params,
            check_robots=check_robots,
            retries=retries,
            ok_statuses=ok_statuses,
            headers=headers,
        )

    def post(
        self,
        url: str,
        json: dict | None = None,
        retries: int | None = None,
        ok_statuses: tuple[int, ...] = (200,),
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self.request("POST", url, json=json, retries=retries, ok_statuses=ok_statuses, headers=headers)

    def request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        json: dict | None = None,
        check_robots: bool = False,
        retries: int | None = None,
        ok_statuses: tuple[int, ...] = (200,),
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        if check_robots and not self.allowed_by_robots(url):
            raise FetchError(f"disallowed by robots.txt: {_safe(url)}")
        host = urlsplit(url).netloc
        attempts = (self.cfg.max_retries if retries is None else retries) + 1
        last_error = "no attempt made"
        for attempt in range(attempts):
            self._wait_for_host(host)
            self.requests += 1
            what = f"{method} {_safe(url)}"
            tries = f"attempt {attempt + 1}/{attempts}"
            started = time.monotonic()
            try:
                resp = self._client.request(method, url, params=params, json=json, headers=headers)
            except httpx.HTTPError as e:
                last_error = f"{type(e).__name__}"
                self._count(f"error_{last_error}")
                delay = self.cfg.backoff_s * (2**attempt)
                log.warning(
                    "%s -> %s after %.1fs (%s)%s",
                    what,
                    last_error,
                    time.monotonic() - started,
                    tries,
                    self._then(attempt, attempts, delay),
                )
                if attempt + 1 < attempts:
                    self._sleep(delay)
                continue
            self._count(f"http_{resp.status_code}")
            elapsed = time.monotonic() - started
            if resp.status_code in ok_statuses:
                log.info("%s -> %s in %.1fs (%s)", what, resp.status_code, elapsed, tries)
                return resp
            last_error = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRY_STATUSES:
                log.warning("%s -> %s in %.1fs (%s); not retried", what, last_error, elapsed, tries)
                break
            delay = self._retry_after(resp) or self.cfg.backoff_s * (2**attempt)
            log.warning(
                "%s -> %s in %.1fs (%s)%s", what, last_error, elapsed, tries, self._then(attempt, attempts, delay)
            )
            if attempt + 1 < attempts:
                self._sleep(delay)
        raise FetchError(f"{last_error} after {attempt + 1} attempt(s): {_safe(url)}")

    def download(self, url: str, dest: Path, retries: int | None = None, log_every_mb: int = 200) -> tuple[str, int]:
        """Stream a large file to `dest` without holding it in memory; returns its SHA-256 and size. A failed attempt
        starts again from the beginning, after the same backoff as `request`."""
        host = urlsplit(url).netloc
        attempts = (self.cfg.max_retries if retries is None else retries) + 1
        last_error = "no attempt made"
        for attempt in range(attempts):
            self._wait_for_host(host)
            self.requests += 1
            what, tries = f"GET {_safe(url)}", f"attempt {attempt + 1}/{attempts}"
            started = time.monotonic()
            try:
                with self._client.stream("GET", url) as resp:
                    self._count(f"http_{resp.status_code}")
                    if resp.status_code != 200:
                        last_error = f"HTTP {resp.status_code}"
                        if resp.status_code not in RETRY_STATUSES:
                            log.warning("%s -> %s (%s); not retried", what, last_error, tries)
                            break
                        delay = self._retry_after(resp) or self.cfg.backoff_s * (2**attempt)
                        log.warning("%s -> %s (%s)%s", what, last_error, tries, self._then(attempt, attempts, delay))
                        if attempt + 1 < attempts:
                            self._sleep(delay)
                        continue
                    digest, size, next_log = hashlib.sha256(), 0, log_every_mb
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_bytes(1024 * 1024):
                            f.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                            if size >= next_log * 1024 * 1024:
                                log.info(
                                    "%s: %d MB so far, %.0fs", what, size // (1024 * 1024), time.monotonic() - started
                                )
                                next_log += log_every_mb
                log.info(
                    "%s -> 200, %d MB in %.1fs (%s)", what, size // (1024 * 1024), time.monotonic() - started, tries
                )
                return digest.hexdigest(), size
            except httpx.HTTPError as e:
                last_error = type(e).__name__
                self._count(f"error_{last_error}")
                delay = self.cfg.backoff_s * (2**attempt)
                log.warning("%s -> %s (%s)%s", what, last_error, tries, self._then(attempt, attempts, delay))
                if attempt + 1 < attempts:
                    self._sleep(delay)
        raise FetchError(f"{last_error} after {attempt + 1} attempt(s): {_safe(url)}")

    def _count(self, outcome: str) -> None:
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1

    @staticmethod
    def _then(attempt: int, attempts: int, delay: float) -> str:
        return f"; retrying in {delay:.0f}s" if attempt + 1 < attempts else "; giving up"

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
