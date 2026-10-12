# Persistent Terminal Viewer Design

## Goal

Make `mdview` a fast, single-terminal Markdown browser while keeping `mdview file.md` as a quick view that returns to the shell.

## User flow

- `mdview` opens a picker for Markdown files in the current directory.
- `j` and `k` move the selection; Enter opens the selected file.
- In the preview, `q` returns to the picker. In the picker, `q` exits to the shell.
- `mdview file.md` renders and displays that file inline, then returns to the shell.
- The dedicated picker and preview use the current terminal; they open no visible windows.

## Rendering design

Keep the existing Python, markdown-it-py, WebKitGTK, and Kitty graphics approach. A long-lived renderer process owns one WebKit view on a private Xvfb display. The view converts the selected file to HTML/CSS and snapshots it as a transparent PNG. The terminal UI displays the PNG in left-aligned strips; subsequent files reuse the same WebKit process.

The interactive UI runs in the original terminal. A small line-based request/result channel carries file paths to the renderer and returns the rendered image dimensions and strip paths. The renderer must not create a window on the user's display. The quick-view command may start a renderer for one file and exit after displaying it.

## Rendering behavior

- Use terminal pixel width captured when the session starts; do not resize the render after terminal resizing.
- Keep each image strip at a consistent width and align strip heights to terminal cell rows, avoiding horizontal drift or seams.
- Preserve the existing transparent dark-terminal styling, relative images, tables, strikethrough, and expanded Obsidian-style callouts.
- Keep raw HTML disabled and wikilinks unsupported.
- Treat image transfer and cleanup as part of each view transition so old images do not remain over the picker or next document.

## Boundaries

- The picker lists Markdown files in the current directory. Directory navigation, fuzzy search, editing, live reload, and non-Kitty image fallbacks are out of scope for this iteration.
- The renderer is reused only within the interactive session; it exits when the user quits.
- File or renderer errors appear in the terminal UI and allow returning to the picker or shell.

## Verification

- Exercise picker movement, opening a document, returning to the picker, and quitting in a Kitty terminal.
- Confirm the renderer process is reused across at least two documents and no window appears on the desktop.
- Confirm long-document strips retain equal width and cell-row alignment across a page transition.
- Keep the existing Markdown rendering checks passing and add focused checks for picker navigation and renderer reuse.

## Decisions

Use `j`/`k`, Enter, and `q`; no custom navigation keys are needed. Keep Python for this iteration; the performance goal is met by reusing WebKit rather than changing implementation language.
