# mdviewer

A lightweight Markdown viewer, launched from the terminal, using a system web engine instead of Electron.

## Status

Initial repository setup. The application is not implemented yet.

## Proposed first version

- Open a Markdown file with `mdview file.md` in a native window.
- Render Markdown as HTML with custom CSS.
- Reload the preview when the file changes.
- Edit in an external editor such as Neovim alongside the preview.

Wikilinks and vault features are outside the initial scope. A built-in editor may follow later.

## Decisions still open

- Python with GTK/WebKitGTK, or Rust with a system webview.
- Markdown extensions beyond CommonMark, such as tables and task lists.
- Whether to include an editor in a later version.
- Project license.

See the [repository setup plan](docs/superpowers/plans/2026-10-12-repository-setup.md).
