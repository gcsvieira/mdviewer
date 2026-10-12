# Persistent Terminal Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Vim-keyed Markdown picker and persistent Kitty preview while retaining `mdview file.md` quick view.

**Architecture:** A curses UI stays in the user's terminal and sends Markdown paths to a long-lived WebKitGTK worker under Xvfb. The worker returns transparent PNG strips; Kitty displays one page at a time, and the same worker handles later selections.

**Tech Stack:** Python, stdlib curses/subprocess/JSON, markdown-it-py, Pillow, GTK 3, WebKitGTK 4.1, Xvfb, Kitty.

**Spec:** `docs/superpowers/specs/2026-10-12-persistent-terminal-viewer-design.md`

## Global Constraints

- Do not open visible GUI windows; WebKitGTK runs only on the private Xvfb display.
- `mdview` opens the picker; `mdview file.md` stays a quick view.
- Picker navigation uses `j`/`k`, Enter, and `q`.
- Keep the terminal's initial pixel width for the whole session.
- Keep image strips left-aligned, equal-width, transparent, and row-aligned.
- Prefer cuts before headings or paragraphs; split within a block only when that block exceeds the page height.
- Preserve the current dark style, raw HTML disabled, and existing Markdown extensions.

## Review Focus

- A long paragraph or heading must remain whole when it fits a page; test in Task 1 with adjacent block boundaries.
- A block taller than a page must still render without gaps or lost pixels; test in Task 1 with the row-aligned fallback.
- The last partial strip must align with earlier strips; test in Task 1 with a non-multiple image height.
- A renderer failure must not hang the picker; test in Task 2 with a worker error response and timeout.
- Returning from a preview must remove its Kitty image before redrawing the picker; test in Task 3 by asserting the clear-and-redraw transition.

---

### Task 1: Split rendered pages at Markdown block boundaries

**Files:**
- Modify: `mdview.py`
- Modify: `tests/test_mdview.py`

**Interfaces:**
- Consumes: existing `snapshot(document, target, width)` and `split_image(image, directory, height)`.
- Produces: `split_image(image: Path, directory: Path, max_height: int, row_height: int, boundaries: list[int]) -> list[Path]`. `boundaries` are document pixel offsets at the top of `h1`–`h6` and `p` elements, collected from WebKit after layout.

- [x] Add a failing test that a strip ends at a paragraph/header boundary before the maximum height when available.
- [x] Add a failing test that a block taller than the page falls back to row-aligned slicing.
- [x] Add a failing test that joining all padded strips preserves every source pixel and strip heights are multiples of `row_height`.
- [x] Run `python3 -m unittest discover -s tests`; confirm these tests fail for the current fixed-height slicing.
- [x] Collect block top offsets from the laid-out DOM, choose the furthest available boundary within `max_height`, crop at that document offset, and pad the strip bottom with transparent pixels to the next row boundary. When no block boundary fits, cut at the maximum row-aligned height.
- [x] Run `python3 -m unittest discover -s tests`; confirm all rendering tests pass.

### Task 2: Keep one WebKit renderer alive per interactive session

**Files:**
- Modify: `mdview.py`
- Modify: `tests/test_mdview.py`

**Interfaces:**
- Consumes: Task 1's block-aware `split_image`.
- Produces: newline-delimited JSON worker protocol. Request: `{"path": "absolute/file.md", "width": 1200, "page_height": 700, "row_height": 20}`. Success response: `{"ok": true, "strips": ["/tmp/.../strip-00000.png"]}`. Failure response: `{"ok": false, "error": "message"}`. One response is written for each request.

- [x] Add a failing protocol test that sends two file requests to one worker and receives two successful responses from the same process ID.
- [x] Add a failing protocol test for a missing or unreadable file returning an error response without terminating the worker.
- [x] Run the focused worker tests; confirm they fail before the persistent worker exists.
- [x] Start Xvfb and GTK/WebKit once in a worker subprocess; process each JSON request with the same WebView and return PNG strips through response paths. Keep diagnostics on stderr and bound each request with a timeout.
- [x] Run the focused worker tests and existing renderer tests; confirm they pass.

### Task 3: Add the picker, paged preview, and quick-view integration

**Files:**
- Modify: `mdview.py`
- Modify: `tests/test_mdview.py`
- Modify: `README.md`
- Modify: `mdview`

**Interfaces:**
- Consumes: Task 2's renderer worker protocol.
- Produces: `main()` opens the picker without a file argument and preserves quick mode with a file argument. The picker lists `*.md` and `*.markdown` files in the current directory sorted by name. `j`/`k` select, Enter opens, and `q` exits. Preview `j`/`k` moves between image pages; `q` clears the Kitty image and returns to the picker.

- [x] Add a failing test for picker selection movement and menu/viewer/quit key transitions.
- [x] Add a failing test that returning from preview clears the image before the picker redraws.
- [x] Add a failing test that the picker passes the rendered PNG strip to Kitty.
- [x] Add failing tests for Kitty clear output and a partial renderer response timeout.
- [x] Run the focused UI tests; confirm they fail before the state transitions are implemented.
- [x] Implement the menu and preview in curses on the current terminal; launch and reuse the worker in interactive mode, draw one left-aligned Kitty image page at a time, clear it on return, and terminate the worker on quit. Keep the existing one-file quick view behavior.
- [x] Update `README.md` with picker keys and both launch modes.
- [x] Run the complete test suite, `python3 -m py_compile mdview.py`, and a Kitty/Xvfb smoke test that opens two files, returns to the picker, and exits without a visible window.

## Completion

Success means both CLI modes work, the interactive session reuses one hidden WebKit process across files, Kitty images clear on navigation, block-aware strips remain aligned, tests pass, and the working tree has no accidental generated artifacts.
