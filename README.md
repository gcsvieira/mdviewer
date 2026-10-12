# mdviewer

Render Markdown as a styled, transparent image in a Kitty terminal. The renderer uses system WebKitGTK rather than bundling a browser.

## Try it

Requirements: Kitty, Python 3, GTK 3, WebKitGTK 4.1, Xvfb, `markdown-it-py`, and Pillow.

On Fedora, install the system packages and Python libraries:

```sh
sudo dnf install kitty gtk3 webkit2gtk4.1 xorg-x11-server-Xvfb python3-gobject
python3 -m pip install -r requirements.txt
```

Then run:

```sh
./mdview path/to/file.md
```

The image uses the terminal's current pixel width and keeps its left edge aligned. Long documents are split into transparent PNG strips whose heights align to terminal rows. The terminal returns to the shell when rendering finishes.

Export image strips without Kitty:

```sh
./mdview path/to/file.md --output /tmp/mdview-images --width 1200 --strip-height 800
```

## Rendering

The prototype supports CommonMark, tables, strikethrough, and Obsidian-style callouts such as `> [!NOTE]`. Callouts render expanded. Raw HTML is disabled. Relative images and links use the Markdown file's directory as their base.

The document background is transparent, with a dark-terminal text palette and subtle translucent callout and code backgrounds. The image is pixels, so terminal text selection and search do not work on rendered content.

See the [repository setup plan](docs/superpowers/plans/2026-10-12-repository-setup.md) for the original project scope.
