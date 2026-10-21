"""Bounded same-host website mirroring with deterministic offline URLs."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


@dataclass
class Options:
    url: str
    output: Path
    max_pages: int = 500
    delay: float = 0.25
    external_assets: bool = True
    respect_robots: bool = True
    max_file_mb: int = 50


class Mirror:
    def __init__(self, options: Options, event=None, cancel=None):
        self.options = options
        self.event = event or (lambda *_: None)
        self.cancel = cancel or threading.Event()
        self.start = self.normalize(options.url)
        if not self.start:
            raise ValueError('Enter a valid http:// or https:// website URL.')
        self.host = urlsplit(self.start).netloc.lower()
        self.root = Path(options.output).expanduser().resolve()
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'NeonArchive/1.0 (offline website archiver)'
        self.queue = deque()
        self.scheduled = set()
        self.files = {}
        self.redirects = {}
        self.documents = []
        self.errors = []
        self.pages = self.assets = self.bytes = 0
        self.page_slots = 0
        self.robot = None
        self.last_request = 0.0

    @staticmethod
    def normalize(url):
        try:
            parts = urlsplit(urldefrag(url)[0])
            if parts.scheme.lower() not in ('http', 'https') or not parts.hostname or parts.username or parts.password:
                return None
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))
        except ValueError:
            return None

    def local_path(self, url):
        parts = urlsplit(url)
        # A URL digest avoids collisions, path traversal and unsafe filename characters.
        digest = hashlib.sha256(url.encode()).hexdigest()
        suffix = Path(parts.path).suffix.lower()
        if not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix):
            suffix = '.html'
        return self.root / 'files' / digest[:2] / (digest + suffix)

    def schedule(self, url, page=False):
        url = self.normalize(url)
        if not url or url in self.scheduled:
            return
        same_host = urlsplit(url).netloc.lower() == self.host
        if page and not same_host:
            return
        if not page and not same_host and not self.options.external_assets:
            return
        if page:
            if self.page_slots >= self.options.max_pages:
                return
            self.page_slots += 1
        self.scheduled.add(url)
        self.queue.append((url, page))

    def log(self, message):
        self.event('log', message)

    def fetch(self, url, page):
        if self.robot and urlsplit(url).netloc.lower() == self.host and not self.robot.can_fetch('*', url):
            raise ValueError('Blocked by robots.txt')
        response = None
        # Follow redirects explicitly so page requests cannot leave the selected host.
        for _ in range(11):
            if self.cancel.wait(max(0, self.options.delay - (time.monotonic() - self.last_request))):
                raise InterruptedError('Cancelled')
            if self.robot and urlsplit(url).netloc.lower() == self.host and not self.robot.can_fetch('*', url):
                raise ValueError('Redirect blocked by robots.txt')
            self.last_request = time.monotonic()
            response = self.session.get(url, timeout=(10, 25), stream=True, allow_redirects=False)
            if response.is_redirect or response.is_permanent_redirect:
                target = self.normalize(urljoin(url, response.headers.get('Location', '')))
                response.close()
                if not target or (urlsplit(target).netloc.lower() != self.host and (page or not self.options.external_assets)):
                    raise ValueError('Redirect leaves allowed host')
                url = target
                continue
            break
        else:
            raise ValueError('Too many redirects')
        with response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                if self.cancel.is_set():
                    raise InterruptedError('Cancelled')
                size += len(chunk)
                if size > self.options.max_file_mb * 1024 * 1024:
                    raise ValueError(f'File exceeds {self.options.max_file_mb} MB limit')
                chunks.append(chunk)
            return b''.join(chunks), response.headers.get('Content-Type', '').lower(), url, response.encoding

    def resolve(self, base, value):
        return self.normalize(urljoin(base, value.strip()))

    def process_css(self, text, base, rewrite=None):
        def replace(match):
            value = match.group(2) if match.group(2) is not None else match.group(4)
            url = self.resolve(base, value)
            if not url:
                return match.group(0)
            if rewrite is None:
                self.schedule(url)
                return match.group(0)
            local = rewrite(value)
            return f'url("{local}")' if match.group(2) is not None else f'@import "{local}"'
        pattern = r'''url\(\s*(['"]?)(.*?)\1\s*\)|@import\s+(['"])(.*?)\3'''
        return re.sub(pattern, replace, text, flags=re.I)

    def html_refs(self, soup):
        for tag in soup.find_all(True):
            for attr in ('src', 'poster', 'data'):
                if tag.get(attr) and (attr != 'data' or tag.name == 'object'):
                    yield tag, attr, False
            if tag.get('href') and tag.name in ('a', 'area', 'link'):
                if tag.name == 'link':
                    rel = set(tag.get('rel', []))
                    if not rel.intersection({'stylesheet', 'icon', 'preload', 'modulepreload', 'apple-touch-icon'}):
                        continue
                yield tag, 'href', tag.name in ('a', 'area')

    def process_html(self, text, final_url):
        soup = BeautifulSoup(text, 'html.parser')
        base_tag = soup.find('base', href=True)
        base = urljoin(final_url, base_tag['href']) if base_tag else final_url
        for tag, attr, page in self.html_refs(soup):
            self.schedule(self.resolve(base, tag[attr]), page)
        for tag in soup.find_all(srcset=True):
            # Data URIs contain commas and are deliberately preserved as a whole.
            if 'data:' not in tag['srcset']:
                for item in tag['srcset'].split(','):
                    if item.strip():
                        self.schedule(self.resolve(base, item.strip().split()[0]))
        for tag in soup.find_all(style=True):
            self.process_css(tag['style'], base)
        for tag in soup.find_all('style'):
            self.process_css(tag.get_text(), base)
        return base

    def rewrite_documents(self):
        for url, kind, base, encoding in self.documents:
            path = self.files[url]
            text = path.read_text(encoding='utf-8')

            def rewrite(value):
                absolute = urljoin(base, value)
                target = self.normalize(absolute)
                target = self.redirects.get(target, target)
                if target not in self.files:
                    return absolute if self.normalize(absolute) else value
                fragment = urlsplit(absolute).fragment
                local = Path(os.path.relpath(self.files[target], path.parent)).as_posix()
                return local + ('#' + fragment if fragment else '')

            if kind == 'css':
                text = self.process_css(text, base, rewrite)
            else:
                soup = BeautifulSoup(text, 'html.parser')
                for tag, attr, _ in self.html_refs(soup):
                    tag[attr] = rewrite(tag[attr])
                for tag in soup.find_all(srcset=True):
                    if 'data:' not in tag['srcset']:
                        values = []
                        for item in tag['srcset'].split(','):
                            bits = item.strip().split()
                            if bits:
                                values.append(' '.join([rewrite(bits[0])] + bits[1:]))
                        tag['srcset'] = ', '.join(values)
                for tag in soup.find_all(style=True):
                    tag['style'] = self.process_css(tag['style'], base, rewrite)
                for tag in soup.find_all('style'):
                    tag.string = self.process_css(tag.get_text(), base, rewrite)
                for tag in soup.find_all('base'):
                    tag.decompose()
                # Integrity hashes no longer match rewritten CSS; CSP may forbid local files.
                for tag in soup.find_all(attrs={'integrity': True}):
                    del tag['integrity']
                for tag in soup.find_all('meta'):
                    if tag.get('http-equiv', '').lower() == 'content-security-policy':
                        tag.decompose()
                    if tag.get('charset'):
                        tag['charset'] = 'utf-8'
                    if tag.get('http-equiv', '').lower() == 'content-type':
                        tag['content'] = 'text/html; charset=utf-8'
                text = str(soup)
            path.write_text(text, encoding='utf-8')

    def run(self):
        if self.options.max_pages < 1 or self.options.delay < 0:
            raise ValueError('Page limit must be positive; delay cannot be negative.')
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            if self.options.respect_robots:
                robot_url = urljoin(self.start, '/robots.txt')
                try:
                    data, _, _, _ = self.fetch(robot_url, True)
                    self.robot = RobotFileParser()
                    self.robot.parse(data.decode('utf-8', errors='replace').splitlines())
                except requests.HTTPError as exc:
                    if exc.response.status_code not in (404, 410):
                        raise ValueError('Cannot verify robots.txt; disable the option to proceed intentionally.') from exc
                except (requests.RequestException, ValueError) as exc:
                    raise ValueError(f'Cannot verify robots.txt: {exc}') from exc
            self.schedule(self.start, True)
            while self.queue and not self.cancel.is_set():
                url, page = self.queue.popleft()
                if url in self.files:
                    continue
                try:
                    data, content_type, final_url, encoding = self.fetch(url, page)
                    if ('text/html' in content_type or 'application/xhtml+xml' in content_type) and urlsplit(final_url).netloc.lower() != self.host:
                        raise ValueError('External HTML page skipped')
                    path = self.local_path(final_url)
                    kind = 'html' if 'text/html' in content_type or 'application/xhtml+xml' in content_type else 'css' if 'text/css' in content_type else None
                    if kind:
                        path = path.with_suffix('.html' if kind == 'html' else '.css')
                    elif path.suffix == '.html':
                        media_type = content_type.split(';')[0].strip()
                        extension = '.js' if media_type in ('application/javascript', 'text/javascript') else mimetypes.guess_extension(media_type)
                        path = path.with_suffix(extension or '.bin')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if kind:
                        # requests defaults text/* to Latin-1; HTML's own encoding declaration takes priority.
                        if kind == 'html':
                            from bs4 import UnicodeDammit
                            text = UnicodeDammit(data, is_html=True).unicode_markup or data.decode('utf-8', errors='replace')
                        else:
                            text = data.decode(encoding or 'utf-8', errors='replace')
                        path.write_text(text, encoding='utf-8')
                        base = self.process_html(text, final_url) if kind == 'html' else final_url
                        if kind == 'css':
                            self.process_css(text, base)
                        self.documents.append((final_url, kind, base, encoding))
                    else:
                        path.write_bytes(data)
                    self.files[final_url] = path
                    self.redirects[url] = final_url
                    self.bytes += len(data)
                    if kind == 'html':
                        self.pages += 1
                    else:
                        self.assets += 1
                    self.log(f'SAVED  {final_url}')
                except InterruptedError:
                    break
                except (requests.RequestException, OSError, ValueError) as exc:
                    self.errors.append({'url': url, 'error': str(exc)})
                    self.log(f'SKIP   {url} — {exc}')
                self.event('stats', {'pages': self.pages, 'assets': self.assets, 'bytes': self.bytes, 'pending': len(self.queue), 'errors': len(self.errors)})
            self.log('Rewriting links for offline browsing…')
            self.rewrite_documents()
            start = self.redirects.get(self.start, self.start)
            if start in self.files:
                from html import escape
                entry = self.files[start].relative_to(self.root).as_posix()
                (self.root / 'index.html').write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={escape(entry, quote=True)}"><a href="{escape(entry, quote=True)}">Open archived website</a>', encoding='utf-8')
            report = {'start_url': self.start, 'cancelled': self.cancel.is_set(), 'pages': self.pages, 'assets': self.assets, 'bytes': self.bytes, 'files': {u: str(p.relative_to(self.root)) for u, p in self.files.items()}, 'errors': self.errors}
            (self.root / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            return report
        finally:
            self.session.close()
