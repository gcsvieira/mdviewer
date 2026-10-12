# mdviewer

A lightweight Markdown browser for Kitty. Markdown becomes HTML/CSS, then transparent images rendered by the system WebKitGTK engine. No Electron or visible renderer windows.

## Install

The release installer supports **Linux x86_64 with glibc 2.34 or newer**. It installs a small compiled native launcher at `~/.local/bin/mdview`, the Python application and its virtual environment under `~/.local/share/mdviewer`, and adds the executable directory to your shell's PATH. Python and WebKit remain runtime dependencies; this is not a standalone bundled browser.

Install the system dependencies first.

**Fedora:**

```sh
sudo dnf install kitty python3 python3-pip python3-gobject python3-cairo \
  gtk3 webkit2gtk4.1 xorg-x11-server-Xvfb xorg-x11-xauth curl
```

**Ubuntu 22.04+ / Debian 12+:**

```sh
sudo apt update
sudo apt install kitty python3 python3-venv python3-pip python3-gi \
  python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 xvfb xauth curl
```

These use the distributions' [WebKitGTK packages](https://packages.fedoraproject.org/pkgs/webkitgtk/webkit2gtk4.1/) and [WebKit 4.1 introspection bindings](https://packages.ubuntu.com/jammy/gir1.2-webkit2-4.1).

Check that `kitten --version` works. Older distribution versions of Kitty may not provide the standalone `kitten` executable; use a current [Kitty release](https://sw.kovidgoyal.net/kitty/binary/) in that case. This release was tested with Kitty 0.47.1.

Then install mdviewer:

```sh
curl -fsSL https://raw.githubusercontent.com/gcsvieira/mdviewer/main/install.sh | sh
```

The installer downloads the latest release, verifies its SHA-256 checksum, and installs `markdown-it-py` and Pillow in a virtual environment that can use the system GTK bindings. Run the same command to update. Existing `~/.config/mdviewer/settings.json` is preserved.

PATH setup supports bash, zsh, and fish. Open a new terminal if the command is not immediately available. You can also invoke `~/.local/bin/mdview` directly.

To inspect the installer before running it:

```sh
curl -fsSL https://raw.githubusercontent.com/gcsvieira/mdviewer/main/install.sh -o install.sh
sh install.sh
```

### Dependencies

- Kitty, including its `kitten` executable, for terminal graphics.
- Python **3.10+**, with `venv` and pip.
- GTK **3**, WebKitGTK **4.1**, PyGObject, and its Cairo bridge.
- Xvfb, `xvfb-run`, and `xauth` for rendering offscreen, including in Wayland sessions.
- curl, tar, and GNU coreutils (`install`, `sha256sum`, `mktemp`, etc.) for the installer.
- `markdown-it-py >=3,<4` and `Pillow >=10,<13`, installed automatically in the application's virtual environment.
- An editor for `e`: `$EDITOR`, then `$VISUAL`, then `vi`.

System packages are installed through your package manager, not automatically by the curl script. A C compiler is needed only when building the launcher from source.

## Quick guide

```sh
mdview                         # Browse the current folder
mdview path/to/note.md          # Quick inline print, then return to the prompt
mdview note.md --output /tmp/mdview-images --width 1200 --strip-height 800
```

Folders appear one level at a time. The picker refreshes automatically when files appear or disappear and preserves selection where possible. Parent navigation stops at the launch folder; explicitly opened symlinks are followed normally.

| Action | Default controls | Vim mode |
| --- | --- | --- |
| Select / scroll or page | Up / Down | `k` / `j` |
| Open file or folder | Right | `l` |
| Return to list / parent | Left | `h` |
| First / last, top / bottom | Home / End | `gg` / `G` |
| Jump to a percentage | `22` + Enter | `22G` |
| Edit selected file | `e` | `e` |
| Settings from the picker | `s` | `s` |
| Exit to your terminal | `q` | `q` |

Enter does not open files. Keyboard modes are exclusive: Vim mode disables arrows and Home/End. Percentage input accepts integers from 0–100; Backspace edits the number, and Escape cancels it. Page jumps snap to the nearest page.

Opening a file displays an animated indeterminate bar. `q` also quits during loading. The background renderer is reused while browsing.

## Settings

Press `s` in the picker. Right or `l` changes the selected option; Space also works. Left or `h`, Escape, or `s` returns to the picker. Changing Vim mode switches the active navigation keys immediately.

Preferences save automatically at **`~/.config/mdviewer/settings.json`**:

```json
{
  "vim-mode": false,
  "file-navigation-style": "scroll",
  "element-color": "white"
}
```

| Setting | Values | Default |
| --- | --- | --- |
| `vim-mode` | `false` / `true` | `false` |
| `file-navigation-style` | `scroll` / `paginated` | `scroll` |
| `element-color` | `white` / `black` | `white` |

White foreground suits dark terminals; black suits light terminals. The terminal background remains transparent. The palette also applies to quick printing and exports. Invalid preferences fall back to defaults.

Scroll mode moves one terminal row at a time. Paginated mode prefers breaks before headings or paragraphs and splits oversized blocks at row boundaries. Resizing adjusts the UI and preview height; the document retains its original rendered width.

## Editing

`e` hands the same terminal to your editor. Commands may contain flags and quoted executable paths:

```sh
EDITOR='nvim -f' mdview
```

On exit, the viewer restores selection or refreshes the preview at the previous scroll position. Editor errors appear in the footer. GUI editors need their wait flag, such as `EDITOR='code --wait'`.

## Build from source

With the system dependencies above, git, and a C compiler installed:

```sh
git clone https://github.com/gcsvieira/mdviewer.git
cd mdviewer
./scripts/build.sh
./install.sh --archive "$PWD/dist/mdviewer-linux-$(uname -m).tar.gz"
```

The build produces a native launcher, a release archive containing the Python sources, and a checksum. It can build for another Linux architecture using that machine's native compiler; published release downloads currently cover x86_64.

For development without installing:

```sh
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
./mdview
python3 -m unittest discover -s tests
```

The installer accepts `--prefix DIRECTORY` and `--no-path` for custom installs. Uninstall by removing `~/.local/bin/mdview` and `~/.local/share/mdviewer`; keep `~/.config/mdviewer` to retain preferences.

## Rendering and limits

CommonMark, tables, strikethrough, relative images, and expanded Obsidian-style callouts (`> [!NOTE]`) are supported. Raw HTML and wikilinks are not supported. Images remain left-aligned, with transparent backgrounds and Obsidian-inspired typography.

Rendered content is pixels, so terminal text selection and searching do not work within it. The viewer currently requires Kitty and Linux. It uses system WebKitGTK rather than bundling a browser engine.
