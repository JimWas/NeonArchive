# NEON ARCHIVE developer documentation

This guide describes the implementation in `app.py` and `scraper.py`. Start with [README.md](README.md) for installation and usage; record future changes in [changelog.md](changelog.md).

## Repository map

- `app.py`: Qt application entry point, window, animation, worker thread, and UI styling.
- `scraper.py`: GUI-independent HTTP crawling, discovery, saving, rewriting, and reporting.
- `requirements.txt`: compatible dependency ranges, not a reproducible dependency lock.
- `Launch.command`: zsh launcher for macOS that bootstraps `.venv` and runs the GUI.
- `Nasalization.otf`: supplied display font, loaded relative to `app.py`.
- `tests/test_scraper.py`: standard-library unittest suite with a temporary local HTTP fixture.
- `preview.png`: saved interface preview; not required at runtime.
- `.gitignore`: excludes the virtual environment, Python caches, and macOS metadata.

There is currently no build configuration, CLI argument parser, installer, CI configuration, database, resume store, or application settings file.

## Architecture and lifecycle

### Desktop layer

`Window` creates the inputs, counters, log, buttons, and stylesheet. `Matrix` paints the background; its Qt timer advances every 90 ms. The font is registered with `QFontDatabase`; Arial is the fallback if registration fails.

`Window.start()` normalizes the input URL, builds a timestamped output directory, constructs `Options`, and starts a `Worker`. Inputs are disabled while a job runs. The progress bar is indeterminate because discovery changes the amount of remaining work.

`Worker` subclasses `QThread`. It creates and runs a `Mirror` inside `run()` and sends Qt signals back to the main thread:

- `update(str, object)` forwards crawler log and stats events.
- `finished_report(object)` delivers the completed or cancelled report.
- `failed(str)` delivers an unexpected/fatal error message.
- The inherited `finished` signal triggers UI cleanup and `deleteLater()`.

Do not manipulate widgets from the crawler or worker thread. Keep HTTP and parsing work in the worker; use signals for UI updates. The log inserts messages as plain text and retains at most 1,500 text blocks.

`Window.stop()` sets the worker's `threading.Event`. The worker is not forcibly terminated. Closing an active window requests cancellation and ignores that close event so finalization can complete.

### Crawler layer

A `Mirror` is intended for one run. `run()`:

1. Validates the page limit and delay, creates the output directory, and checks robots.txt if enabled.
2. Schedules the starting URL as a page request.
3. Pops queued URLs in FIFO order, fetches responses sequentially, classifies content, saves files, and discovers new references.
4. Records recoverable per-URL failures and emits progress events.
5. When the queue empties or cancellation is observed, rewrites downloaded HTML/CSS against the files actually saved.
6. Writes an entry `index.html` if the starting URL was saved, writes `manifest.json`, and returns its report.
7. Closes the Requests session in `finally`.

Fatal setup or finalization errors propagate to `Worker.failed`. A manifest is not guaranteed if the run fails before report creation. A successful return can contain errors or zero saved pages; inspect the report rather than assuming completeness.

## Core API

### Options

`Options` is a dataclass with these fields:

- `url: str`: required HTTP(S) start URL. The core requires a scheme; only the GUI adds a missing `https://`.
- `output: Path`: required archive root. The core uses this exact directory; only the GUI creates a timestamped child folder.
- `max_pages: int = 500`: maximum number of URLs first scheduled as page links, including the start URL.
- `delay: float = 0.25`: minimum interval in seconds between HTTP request starts, including redirects.
- `external_assets: bool = True`: allows off-host supporting-file requests.
- `respect_robots: bool = True`: checks start-host robots rules.
- `max_file_mb: int = 50`: maximum bytes read per response, calculated as this value multiplied by 1,024 × 1,024. This setting is available through Python, not the GUI.

The GUI accepts page limits from 1 to 100,000 and delays from 0 to 60 seconds. The core checks only that `max_pages >= 1` and `delay >= 0`; callers should also provide sensible values for other fields.

### Use without the GUI

```python
from pathlib import Path
from threading import Event

from scraper import Mirror, Options


def on_event(kind, payload):
    if kind == "log":
        print(payload)
    elif kind == "stats":
        print(f"Pages: {payload['pages']}; pending: {payload['pending']}")


cancel = Event()
options = Options(
    url="https://example.com/",
    output=Path("archives/example-run"),
    max_pages=100,
    delay=0.5,
    external_assets=True,
    respect_robots=True,
)
report = Mirror(options, event=on_event, cancel=cancel).run()
print(report["pages"], report["errors"])
```

This is a synchronous call. To cancel while it runs, another thread must call `cancel.set()`. Use a fresh `Mirror` and a new output directory for every job; reusing a populated directory can leave stale files and is not a supported resume operation.

### Event contract

The optional callback receives `(kind, payload)` synchronously on the thread calling `run()`:

- `log`: payload is a human-readable string, such as a saved URL, skip reason, or finalization message.
- `stats`: payload is a dictionary with integer `pages`, `assets`, `bytes`, `pending`, and `errors` fields.

Callbacks should be fast and should not raise exceptions. Stats are emitted after processed queue entries; they are not a per-chunk transfer stream or a guaranteed final snapshot on cancellation. The returned report is the final result.

## URL discovery and scope

`normalize()` removes fragments, lowercases scheme and network location, supplies `/` for an empty path, and accepts HTTP(S) URLs without embedded username/password credentials. Query strings are preserved. It does not canonicalize query ordering, default ports, or equivalent paths.

Host scope compares `urlsplit(url).netloc.lower()` against the start URL. It is not a registrable-domain comparison. Subdomains and aliases are separate; schemes may differ. Fragments do not cause extra fetches and are restored in rewritten links.

`scheduled` deduplicates normalized URLs. `queue` holds `(url, page)` tuples. The first scheduling classification wins; a later reference does not promote an asset to a page. `files` maps final response URLs to paths. `redirects` maps requested URLs to their final response URLs for rewriting.

### HTML discovery

`html_refs()` yields:

- `src` and `poster` attributes as supporting files.
- `data` on `object` elements as supporting files.
- `href` on `a` and `area` elements as page links.
- `href` on `link` elements whose `rel` includes stylesheet, icon, preload, modulepreload, or apple-touch-icon as supporting files.

`process_html()` also inspects basic comma-separated `srcset`, inline `style` attributes, and `style` blocks. A source set containing `data:` is preserved as a whole. A `base href` affects discovery and rewriting.

`process_css()` uses a regular expression for `url(...)` and quoted `@import` references. This is not a complete CSS parser. HTML is recognized through `text/html` or `application/xhtml+xml` response content types; CSS through `text/css`. Incorrect/missing server content types can prevent discovery.

### Page-limit semantics

Only `schedule(..., page=True)` consumes a page slot. Failed or blocked page-link URLs still consume their slots. Supporting files are not bounded by this limit. Same-host HTML returned through a supporting-file reference, such as an iframe, is parsed and counted as a page without consuming an additional page slot. Therefore `max_pages` is not a hard cap on the report's HTML page count. There is no global request, byte, disk, queue-size, or elapsed-time limit.

Off-host HTML discovered as a supporting file is rejected after fetching, so the external-assets option can still cause an external HTML request even though its response is not saved.

## HTTP, robots, and cancellation

A single `requests.Session` identifies itself as `NeonArchive/1.0 (offline website archiver)`. There is no custom authentication workflow, retry policy, parallel download pool, or application response cache.

Requests use a 10-second connection timeout and a 25-second read timeout. The read timeout limits a stalled read, not the total response duration. Redirects are followed explicitly with a bounded loop of 11 request attempts. Page requests cannot redirect off-host; asset redirects can when external assets are enabled.

Responses are read in 65,536-byte chunks into memory before being written. The size limit applies to bytes yielded by Requests, including decoded content when transfer decompression occurs. An archive can contain many individually permitted files.

The start host's `/robots.txt` is fetched before crawling. HTTP 404/410 means no rules. Other HTTP, network, or validation failures during that check stop the run. Rules are checked with `can_fetch('*', url)`, including same-host redirect targets. Robots files for external asset hosts are not fetched. `Crawl-delay` is not applied; the configured delay controls pacing.

Cancellation is checked during request pacing, response chunk iteration, and the queue loop. It cannot interrupt a currently blocking network call immediately, and final rewriting is not cancellable. Normal cancellation preserves saved files and writes a partial manifest. Cancellation during the initial robots check can propagate as a setup failure instead of producing a partial report.

## Archive storage and rewriting

The output layout is:

```text
<archive-folder>/
  index.html
  manifest.json
  files/
    <first-two-digest-characters>/
      <full-sha256-digest>.<extension>
```

`local_path()` hashes the full normalized URL with SHA-256, including its query string. Remote paths are not used as local directories. A short alphanumeric source extension is retained initially; HTML/CSS extensions are set from content type. When the initial extension is `.html` but the response is neither HTML nor CSS, the crawler infers an extension from MIME type, with explicit JavaScript handling and `.bin` fallback.

HTML encoding is detected with Beautiful Soup's `UnicodeDammit`. CSS uses the response encoding or UTF-8 fallback. Rewritten text is saved as UTF-8; binary files retain response bytes. HTTP headers are not archived.

Rewriting runs after discovery so it can distinguish saved and missing targets:

- Saved references become relative paths, with URL fragments preserved.
- Unsaved supported HTTP(S) references become absolute online URLs.
- Non-HTTP references, such as data URLs, are preserved.
- HTML `base` elements, integrity attributes, and CSP meta tags are removed.
- Existing charset declarations are updated to UTF-8.

The archive is a functional adaptation, not an exact forensic copy. JavaScript and unsupported HTML attributes are not rewritten. Original unmodified HTML/CSS is not retained separately. A local server may be needed for module scripts, fetch requests, and other browser origin restrictions.

### Manifest contract

`run()` returns the same dictionary serialized to `manifest.json`:

- `start_url`: normalized requested starting URL.
- `cancelled`: whether the cancellation event is set at final report creation.
- `pages`: successful HTML saves.
- `assets`: successful non-HTML saves.
- `bytes`: total response-body bytes for successful saves, before link rewriting; excludes robots.txt and rejected/failed responses.
- `files`: mapping of final response URLs to archive-relative paths.
- `errors`: list of objects containing `url` and a human-readable `error` string.

Requested redirect aliases are held in memory but are not exported separately in the manifest. Counters describe saves, not necessarily unique final URLs when several aliases redirect to the same resource. Error strings have no stable machine-readable codes. The manifest has no explicit schema version; add one before introducing incompatible consumers or format changes.

## Testing and development workflow

Run `python -m unittest discover -s tests -v` in the activated environment. The suite uses temporary directories and a loopback-only HTTP server on an automatically assigned port. It does not require external websites.

The four tests cover:

- Crawl discovery and local link repair, query variants, same-host redirects, external redirect rejection, robots exclusions, nested CSS assets, UTF-8 text, and extensionless images.
- Page-link limiting while continuing to save supporting files.
- A pre-cancelled run writing a report when robots checking is disabled.
- URL-hashed path containment, query-specific paths, and rejection of file URLs and embedded credentials.

Coverage does not yet include all redirect-loop cases, robots setup failures, network timeouts, oversized responses, mid-transfer cancellation, malformed documents, external CDNs, or GUI worker lifecycle behavior.

For a quick GUI render check from the project folder:

```sh
QT_QPA_PLATFORM=offscreen python - <<'PY'
from PySide6.QtWidgets import QApplication
from app import Window

app = QApplication([])
window = Window()
window.show()
app.processEvents()
assert window.start_button.isEnabled()
assert not window.stop_button.isEnabled()
assert window.grab().save('/tmp/neon-archive-preview.png')
window.close()
PY
```

This checks construction and rendering, not a full interactive crawl. On a real desktop, also test starting a local fixture crawl, aborting, waiting for finalization, opening its entry page, starting a second job, and closing during a job. Check the minimum window size and verify font loading. The development smoke check used macOS; Windows and Linux need separate testing.

## Making changes

### Add a download option

Add the field to `Options`, use it in the crawler, and pass it from `Window.start()` with an associated GUI control if needed. Prefer keyword arguments when extending construction: the existing GUI currently passes several fields positionally, so inserting/reordering dataclass fields can silently change behavior. Update defaults and limitations in both documentation files.

### Add a resource type

Update discovery and rewriting together. For an HTML attribute, consider whether it belongs in `html_refs()` or needs separate parsing. Add a local fixture that proves the resource is fetched and its saved reference resolves. Avoid fetching arbitrary text that merely resembles a URL.

### Change URL policy or storage

Keep host restrictions consistent in scheduling and redirects. Preserve the relationship between normalized URL keys, hashed paths, final-URL mappings, and rewritten fragments. Extend fixtures for ports, schemes, queries, aliases, and redirects before changing canonicalization. Retain path containment and avoid incorporating untrusted remote path components directly into filesystem paths.

### Change the interface

Most layout and styles live in `Window.__init__()`. Object names select stylesheet rules. Animation behavior lives in `Matrix`; telemetry formatting lives in `on_update()`. Keep the font path relative to the module so launch location does not affect loading. Preserve signal-based communication and cooperative thread shutdown.

### Add packaging or releases

Include `Nasalization.otf` as a runtime asset and test its location in the packaged build. Establish software/font licensing, supported platforms, dependency pinning, version metadata, and automated checks before distributing a release. Record completed changes in the changelog. These are future development tasks, not features already implemented.

## Troubleshooting

- **Missing imports:** activate the project's `.venv` and reinstall `requirements.txt`. The launcher checks imports, not whether installed versions still match the declared ranges.
- **Launcher exits:** run `python app.py` from the activated environment to read the error. Python, zsh, and access to install packages are required for launcher setup.
- **No pages saved:** inspect the log and manifest, check robots rules, and confirm the start URL does not redirect to a different host.
- **Assets missing:** inspect per-URL errors, response size limits, external-assets settings, and whether the site constructs URLs in JavaScript.
- **Abort seems slow:** a network operation may be waiting on its timeout, or link rewriting may still be running.
- **Offline page still contacts the internet:** missing/unsupported links retain online destinations, and scripts can make their own requests. The archive is not an isolated browser environment.
- **Local tests cannot bind a socket:** run them in an environment that permits loopback servers; this is an environment restriction rather than a crawler assertion failure.
