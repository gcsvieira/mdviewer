# mdviewer

Render Markdown as a styled, transparent image in a Kitty terminal. The renderer uses system WebKitGTK rather than bundling a browser.

## Try it

Requirements: Kitty, Python 3, GTK 3, WebKitGTK 4.1, Xvfb, `markdown-it-py`, and Pillow.

On Fedora, install the system packages and Python libraries:

```sh
sudo dnf install kitty gtk3 webkit2gtk4.1 xorg-x11-server-Xvfb python3-gobject
python3 -m pip install -r requirements.txt
```

Open the folder and Markdown picker in the current directory:

```sh
./mdview
```

The default controls are Up/Down to select, Right to open a file or folder, Left to return to the containing list or parent folder, and Home/End to jump to the edges. Enter does not open files. `q` exits from every screen, including while a file is loading.

Folders are shown one level at a time. The current folder refreshes automatically while idle, preserving the selected item when files appear or disappear. Parent navigation stops at the directory where the session started; explicit symlinks are followed normally.

Press `s` in the picker to open settings. Use Right or Space to change the selected value; Left, Escape, or `s` returns to the picker. Preferences are saved immediately in `~/.config/mdviewer/settings.json`:

| Setting | Default | Options |
| --- | --- | --- |
| `vim-mode` | off | Arrow/Home/End controls, or exclusively `hjkl` and `gg`/`G` |
| `file-navigation-style` | scroll | Scroll one terminal row, or move between paragraph-aware pages |
| `element-color` | white | White or black foreground for the UI and rendered Markdown |

When Vim mode is on, `j`/`k` selects or scrolls, `l` opens/changes a setting, `h` returns, and `gg`/`G` jumps to the edges. Arrow keys and Home/End are disabled in this mode. Footer hints show only the active scheme. Escape and `s` still leave settings.

In a preview, type a percentage from 0 to 100 followed by Enter in arrow mode, or `G` in Vim mode. Backspace edits the number and Escape cancels it. Other navigation keys cancel the pending number and perform their usual action. Paginated jumps snap to the nearest page; the last page is 100%.

Opening a file shows an animated indeterminate bar while the background renderer works. The renderer stays alive between documents and runs on a private Xvfb display, so no rendering window appears on the desktop.

Press `e` in the list or preview to edit the file in the same terminal. The viewer uses a nonempty `$EDITOR`, then `$VISUAL`, then `vi`. Commands can include arguments and quoted executable paths; for example:

```sh
EDITOR='nvim -f' ./mdview
```

When the editor exits, the viewer restores the list selection or refreshes the preview at the previous scroll position. Editor errors appear in the footer. If you use a GUI editor, include its wait flag (such as `code --wait`) so the viewer resumes after editing finishes.

For one quick inline view that returns to the prompt:

```sh
./mdview path/to/file.md
```

The full document is rendered once. Scroll mode moves a viewport over the image; paginated mode prefers breaks before headings or paragraphs and splits oversized blocks at row boundaries. Images use the terminal's initial pixel width and stay left-aligned.

Resizing adjusts the menu and preview height without rerendering the document. Its original layout width is retained.

The file list uses a magenta selection marker, folder names, and modification times. Hidden directories and `node_modules` are excluded. The renderer forces GTK's X11 backend on the private Xvfb display, even in a Wayland session.

Quick inline output and exports still use image strips. Long documents break before headings or paragraphs when possible, then split into row-aligned strips.

Export image strips without Kitty:

```sh
./mdview path/to/file.md --output /tmp/mdview-images --width 1200 --strip-height 800
```

## Rendering

The prototype supports CommonMark, tables, strikethrough, and Obsidian-style callouts such as `> [!NOTE]`. Callouts render expanded. Raw HTML is disabled. Relative images and links use the Markdown file's directory as their base.

The document background is transparent, with the selected white or black foreground palette and subtle translucent callout and code backgrounds. The image is pixels, so terminal text selection and search do not work on rendered content.

See the [repository setup plan](docs/superpowers/plans/2026-10-12-repository-setup.md) for the original project scope.
