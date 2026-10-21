import functools
import json
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bs4 import BeautifulSoup

from scraper import Mirror, Options


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/second.html')
            self.end_headers()
        elif self.path == '/asset':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.end_headers()
            self.wfile.write(b'png fixture')
        elif self.path == '/leave':
            self.send_response(302)
            self.send_header('Location', 'http://example.invalid/')
            self.end_headers()
        else:
            super().do_GET()


class MirrorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        site = self.root / 'site'
        site.mkdir()
        (site / 'index.html').write_text('''<!doctype html><meta charset="utf-8"><h1>Café</h1>
        <link rel="stylesheet" href="style.css"><img src="image.svg"><img src="/asset">
        <img srcset="image.svg 1x, image2.svg 2x"><script src="app.js"></script>
        <a href="/redirect#section">Next</a><a href="/second.html?q=1">Query</a>
        <a href="/blocked.html">Blocked</a><a href="/leave">Leave</a>
        <a href="https://example.invalid/">External</a>''')
        (site / 'second.html').write_text('<a href="/">Home</a><div id="section">Page two</div>')
        (site / 'blocked.html').write_text('Forbidden')
        (site / 'robots.txt').write_text('User-agent: *\nDisallow: /blocked.html\n')
        (site / 'style.css').write_text('@import "more.css"; body { background: url("image.svg"); }')
        (site / 'more.css').write_text('@font-face {src: url(font.woff2)}')
        for name in ['image.svg', 'image2.svg', 'font.woff2', 'app.js']:
            (site / name).write_bytes(b'test asset')
        handler = functools.partial(QuietHandler, directory=str(site))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def run_mirror(self, **kwargs):
        output = self.root / 'archive'
        mirror = Mirror(Options(self.url, output, delay=0, **kwargs))
        report = mirror.run()
        return mirror, report, output

    def test_crawl_assets_queries_redirects_and_rewrite(self):
        mirror, report, output = self.run_mirror()
        self.assertEqual(report['pages'], 3)
        self.assertEqual(report['assets'], 7)
        self.assertTrue((output / 'index.html').exists())
        self.assertEqual(len(report['errors']), 2)
        self.assertEqual(mirror.files[self.url + 'asset'].suffix, '.png')
        self.assertNotIn(self.url + 'blocked.html', report['files'])
        self.assertTrue(any('allowed host' in e['error'] for e in report['errors']))
        saved = mirror.files[self.url]
        soup = BeautifulSoup(saved.read_text(), 'html.parser')
        self.assertIn('Café', soup.get_text())
        for tag, attr in [(soup.img, 'src'), (soup.link, 'href'), (soup.script, 'src')]:
            self.assertTrue((saved.parent / tag[attr]).resolve().exists())
        next_link = soup.find('a')['href']
        self.assertTrue(next_link.endswith('#section'))
        self.assertTrue((saved.parent / next_link.split('#')[0]).resolve().exists())
        css = mirror.files[self.url + 'style.css'].read_text()
        self.assertNotIn('"image.svg"', css)
        self.assertIn('url("', css)
        self.assertEqual(json.loads((output / 'manifest.json').read_text())['pages'], 3)

    def test_page_limit(self):
        _, report, _ = self.run_mirror(max_pages=1)
        self.assertEqual(report['pages'], 1)
        self.assertGreater(report['assets'], 0)

    def test_cancel_still_writes_report(self):
        cancel = threading.Event()
        cancel.set()
        output = self.root / 'cancelled'
        mirror = Mirror(Options(self.url, output, respect_robots=False), cancel=cancel)
        report = mirror.run()
        self.assertTrue(report['cancelled'])
        self.assertEqual(report['pages'], 0)
        self.assertTrue((output / 'manifest.json').exists())

    def test_paths_are_safe_and_query_specific(self):
        mirror = Mirror(Options(self.url, self.root / 'out'))
        first = mirror.local_path(self.url + '../../etc/passwd?q=1')
        second = mirror.local_path(self.url + '../../etc/passwd?q=2')
        self.assertTrue(first.is_relative_to(mirror.root))
        self.assertNotEqual(first, second)
        self.assertIsNone(Mirror.normalize('file:///etc/passwd'))
        self.assertIsNone(Mirror.normalize('http://user:pass@example.com'))


if __name__ == '__main__':
    unittest.main()
