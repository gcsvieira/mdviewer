# mdviewer

Render Markdown as a styled, transparent image in a Kitty terminal. The renderer uses system WebKitGTK rather than bundling a browser.

## Try it

Requirements: Kitty, Python 3, GTK 3, WebKitGTK 4.1, Xvfb, `markdown-it-py`, and Pillow.

On Fedora, install the system packages and Python libraries:

```sh
sudo dnf install kitty gtk3 webkit2gtk4.1 xorg-x11-server-Xvfb python3-gobject
python3 -m pip install -r requirements.txt
```

Open the Markdown picker for the current directory and its subdirectories:

```sh
./mdview
```

Use Up/Down or `j`/`k` to choose a file. Enter, Right, or `l` opens it; Left or `h` returns to the list. Press `q` in either screen to exit to the shell. The WebKit renderer stays alive while you browse and runs on a private Xvfb display, so no window appears on your desktop.

Home or `gg` jumps to the first file or the top of the preview; End or `G` jumps to the last file or the bottom of the preview.

Press `e` in the list or preview to edit the file in the same terminal. The viewer uses a nonempty `$EDITOR`, then `$VISUAL`, then `vi`. Commands can include arguments and quoted executable paths; for example:

```sh
EDITOR='nvim -f' ./mdview
```

When the editor exits, the viewer restores the list selection or refreshes the preview at the previous scroll position. Editor errors appear in the footer. If you use a GUI editor, include its wait flag (such as `code --wait`) so the viewer resumes after editing finishes.

For one quick inline view that returns to the prompt:

```sh
./mdview path/to/file.md
```

In the preview, use Down/Up or `j`/`k` to scroll down/up one terminal row and Left or `h` to return to the file list. Press `q` to exit the program. The full document is rendered once; scrolling moves a viewport over that image. Images use the terminal's initial pixel width and stay left-aligned. Scroll view is the default; an optional paginated view is deferred.

Resizing adjusts the menu and preview height without rerendering the document. Its original layout width is retained.

The file list uses a magenta selection marker, relative paths, and modification times. Hidden directories and `node_modules` are excluded. The renderer forces GTK's X11 backend on the private Xvfb display, even in a Wayland session.

Quick inline output and exports still use image strips. Long documents break before headings or paragraphs when possible, then split into row-aligned strips.

Export image strips without Kitty:

```sh
./mdview path/to/file.md --output /tmp/mdview-images --width 1200 --strip-height 800
```

## Rendering

The prototype supports CommonMark, tables, strikethrough, and Obsidian-style callouts such as `> [!NOTE]`. Callouts render expanded. Raw HTML is disabled. Relative images and links use the Markdown file's directory as their base.

The document background is transparent, with a dark-terminal text palette and subtle translucent callout and code backgrounds. The image is pixels, so terminal text selection and search do not work on rendered content.

See the [repository setup plan](docs/superpowers/plans/2026-10-12-repository-setup.md) for the original project scope.
