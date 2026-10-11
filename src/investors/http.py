"""Šetrné HTTP stahování: diskový cache, rate-limit na doménu a respektování robots.txt.

Každá odpověď se uloží do data/cache, takže opakovaný běh pipeline nevytváří
žádné další požadavky. SHA-256 obsahu slouží jako otisk dokladu (evidence).
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

USER_AGENT = (
    "Mozilla/5.0 (compatible; investors-research/0.1; "
    "+https://github.com/ElectricKota/Clientelo-a)"
)

# Minimální rozestup mezi požadavky na stejnou doménu (sekundy).
DEFAULT_DELAY = 1.5
DOMAIN_DELAY = {
    "ares.gov.cz": 0.4,
    "jerrs.cnb.cz": 2.0,
}

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"


@dataclass
class Response:
    url: str
    status: int
    text: str
    sha256: str
    fetched_at: str
    from_cache: bool


class Fetcher:
    def __init__(self, cache_dir: Path = CACHE_DIR, offline: bool = False):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "cs,en;q=0.8"},
            timeout=60,
            follow_redirects=True,
        )
        self.network_requests = 0

    # -- cache -------------------------------------------------------------
    def _key(self, method: str, url: str, body: str | None) -> Path:
        h = hashlib.sha1(f"{method} {url} {body or ''}".encode()).hexdigest()
        return self.cache_dir / h[:2] / f"{h}.json"

    def _read_cache(self, path: Path) -> Response | None:
        if not path.exists():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return Response(d["url"], d["status"], d["text"], d["sha256"], d["fetched_at"], True)

    def _write_cache(self, path: Path, r: Response) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"url": r.url, "status": r.status, "text": r.text,
                 "sha256": r.sha256, "fetched_at": r.fetched_at},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # -- politeness --------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(f"{base}/robots.txt")
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._robots[base] = rp
        rp = self._robots[base]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        delay = DOMAIN_DELAY.get(host, DEFAULT_DELAY)
        wait = self._last.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    # -- public API --------------------------------------------------------
    def request(self, method: str, url: str, *, data: dict | None = None,
                json_body: dict | None = None, use_cache: bool = True) -> Response:
        body = None
        if data is not None:
            body = json.dumps(data, sort_keys=True)
        elif json_body is not None:
            body = json.dumps(json_body, sort_keys=True)
        path = self._key(method, url, body)
        if use_cache:
            cached = self._read_cache(path)
            if cached:
                return cached
        if self.offline:
            raise RuntimeError(f"offline režim, chybí v cache: {url}")
        if not self._allowed(url):
            raise PermissionError(f"robots.txt zakazuje: {url}")

        for attempt in range(3):
            self._throttle(url)
            try:
                self.network_requests += 1
                r = self.client.request(method, url, data=data, json=json_body)
                break
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
        text = r.text
        resp = Response(
            url=str(r.url),
            status=r.status_code,
            text=text,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            from_cache=False,
        )
        # Chyby serveru necacheujeme, 404 ano (stabilní odpověď).
        if r.status_code < 500 and r.status_code != 429:
            self._write_cache(path, resp)
        return resp

    def get(self, url: str, **kw) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Response:
        return self.request("POST", url, **kw)
