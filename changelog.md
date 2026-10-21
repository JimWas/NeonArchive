# Changelog

This log records changes present in this project. Dates describe local development work, not published releases. There is no formal release/tag process yet; the HTTP user-agent's `1.0` identifier is not a package release version.

## Unreleased

### Documentation — 2026-10-21

- Expanded `README.md` with setup, usage, crawl scope, limitations, testing, and distribution notes.
- Added `documentation.md` for developer onboarding, crawler internals, Qt threading, configuration, callbacks, output format, testing, and extension guidance.
- Added this changelog to establish a maintained history.
- No application behavior changes in this documentation update.

## Initial implementation — 2026-10-19

### Added

- Python website crawler with a FIFO queue, URL deduplication, same-host page discovery, and optional external supporting files.
- HTML asset discovery, basic image source-set handling, CSS imports, and CSS URL discovery.
- Offline HTML/CSS link rewriting, URL-hashed filenames, extension inference for extensionless resources, and a generated archive entry page.
- JSON manifests with URL-to-file mappings, transfer counters, cancellation status, and per-URL errors.
- Configurable page-link limit, request delay, robots.txt enforcement, and a per-response size limit.
- Explicit redirect handling, connection/read timeouts, and cooperative cancellation with partial-archive finalization.
- PySide6 desktop GUI with background crawling, telemetry, activity logs, destination selection, and an offline-site button.
- Animated Matrix backdrop and mission-control styling using the supplied Nasalization font.
- macOS launcher, virtual-environment setup instructions, and minimal Qt Essentials dependencies.
- Four local-fixture tests covering crawling and rewriting, page limits, pre-cancelled runs, and safe/query-specific paths. The crawl fixture also covers robots exclusions, redirects, nested CSS resources, UTF-8 HTML, and extensionless images.

## Maintaining this file

Add new entries under **Unreleased**, grouped by Added, Changed, Fixed, or Removed as appropriate. Describe observable behavior and compatibility changes. When formal releases begin, move the relevant entries into a dated version section matching the actual release tag. Do not describe planned features as completed work.
