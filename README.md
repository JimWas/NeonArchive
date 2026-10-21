# NEON ARCHIVE

A Python desktop website scraper that builds browsable offline copies of linked pages and supporting files. The GUI combines animated Matrix rain, cyberpunk colors, mission telemetry, and the included Nasalization font.

## Quick start

Use Python 3.10 or newer and a desktop environment supported by the installed Qt version. Development verification so far has been on macOS with Python 3.13; other platforms need their own verification.

From the project folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows, use `py -m venv .venv` and activate with `.venv\Scripts\activate.bat` in Command Prompt or `.venv\Scripts\Activate.ps1` in PowerShell.

On macOS, double-click **Launch.command**. It changes to the project folder, creates `.venv` if needed, installs dependencies if their imports fail, and starts the app. Python 3 must already be installed. If the launcher is not executable, run `chmod +x Launch.command` from this folder.

## Archive a website

1. Enter the website's final canonical URL, such as `https://example.com/`. The GUI adds `https://` if no scheme is supplied.
2. Choose an archive destination. The default is `~/Downloads/Neon Archives`.
3. Set a page limit and delay. Defaults are **500 page-link requests** and **0.25 seconds** between request starts.
4. Choose whether to respect `robots.txt` and include external supporting files. Both default to enabled.
5. Select **Initiate Archive** and watch the counters and activity log.
6. Select **Open Offline Site** when the entry page has been saved.

Each GUI run creates a separate `<hostname>-<timestamp>` folder. **Abort** requests cancellation and allows final link repair to finish. Closing during a run requests cancellation; close the window again after finalization.

## What is downloaded

- Linked pages on the same exact host, including query-string variants.
- Referenced stylesheets, scripts, images, fonts, icons, frames, and media sources.
- Resources referenced by CSS imports and `url()` declarations.
- Optional external supporting files, including CDN resources. External HTML is not saved.

The archive contains `index.html` as its entry point, hashed files under `files/`, and `manifest.json` with original URLs, saved paths, counters, and per-URL errors. HTML and CSS are rewritten for offline browsing; they are not byte-for-byte source backups.

## Scope and limitations

Only the exact hostname and port are considered the same host. Subdomains, `www` aliases, and explicit versus implicit ports are distinct. HTTP and HTTPS URLs on the same host are allowed. Page redirects to another host are rejected: start from the final canonical URL.

This downloads public client-side files. It cannot recover private server-side source code, databases, or unpublished files. It does not execute JavaScript, submit forms, discover unlinked pages, read sitemaps, or provide a login workflow. JavaScript imports, API-driven content, streaming playlists, and complex `srcset` syntax are not fully mirrored. Unavailable links can still point online.

The page limit bounds URLs scheduled through page links, not all responses, total assets, memory, or disk use. Each response has a default 50 MiB limit. Downloaded HTML found through a supporting-file reference can also discover links; see the developer guide for details.

Respect for `robots.txt` is enabled by default. Missing robots files (HTTP 404/410) are accepted; other robots-check failures stop the run. Only archive sites you have permission to copy.

## Browse through a local server

If browser restrictions prevent scripts from working with `file://`, serve the archive locally:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory "/path/to/archive-folder"
```

Open `http://127.0.0.1:8000` in your browser. Stop the server with Ctrl+C. This does not restore a site's backend or remote APIs.

## Development

The core crawler can be imported without Qt. The desktop app uses PySide6 Essentials, Requests handles HTTP, and Beautiful Soup parses HTML. Dependency ranges are listed in `requirements.txt`; no lockfile or packaged executable is provided.

Run the automated local-fixture tests:

```sh
python -m unittest discover -s tests -v
```

The tests create a temporary server bound to `127.0.0.1`; the environment must allow local socket binding.

- [Developer documentation](documentation.md): architecture, API, archive format, extension points, and troubleshooting.
- [Changelog](changelog.md): initial implementation and subsequent documentation work.

## Distribution

No project license or font license file is currently included. Confirm the intended software license and the Nasalization font's redistribution terms before distributing a release.
