#!/usr/bin/env python3
"""Render Markdown through the system WebKitGTK engine and display it in Kitty."""
import argparse
import html
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from PIL import Image


STYLE = """
html, body { background: transparent; margin: 0; padding: 0; }
* { box-sizing: border-box; }
body { color: #dadada; font: 16px/1.6 -apple-system, BlinkMacSystemFont,
       'Segoe UI', 'Noto Sans', sans-serif; overflow-wrap: anywhere; }
main { padding: 12px 16px; width: 100%; }
h1, h2, h3, h4, h5, h6 { color: #f0f0f0; line-height: 1.25;
                         margin: 1.3em 0 .55em; font-weight: 650; }
h1 { font-size: 2em; } h2 { font-size: 1.55em; } h3 { font-size: 1.25em; }
main > :first-child { margin-top: 0; }
p, ul, ol, blockquote, pre, table { margin: 0 0 1em; }
a { color: #b5a2f4; text-decoration: underline; }
code { font-family: 'Noto Sans Mono', monospace; font-size: .87em;
       background: rgba(160,160,180,.12); border-radius: 4px; padding: .15em .3em; }
pre { background: rgba(160,160,180,.10); padding: 12px; border-radius: 6px;
      white-space: pre-wrap; overflow-wrap: anywhere; }
pre code { background: transparent; padding: 0; }
blockquote { border-left: 3px solid #858585; padding-left: 14px; color: #bcbcbc; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; max-width: 100%; table-layout: fixed; }
th, td { border: 1px solid rgba(180,180,180,.35); padding: 6px 12px; }
th { background: rgba(180,180,180,.10); }
hr { border: 0; border-top: 1px solid rgba(180,180,180,.3); margin: 24px 0; }
.callout { --accent: 100,170,240; border-left: 3px solid rgb(var(--accent));
           background: rgba(var(--accent),.10); padding: 12px 16px;
           border-radius: 5px; margin-bottom: 1em; }
.callout-title { color: rgb(var(--accent)); font-weight: 650; margin-bottom: 6px; }
.callout > :last-child { margin-bottom: 0; }
.tip, .success, .check, .done { --accent: 90,195,150; }
.warning, .caution, .attention { --accent: 235,175,80; }
.danger, .error, .failure, .fail, .missing, .bug { --accent: 240,110,110; }
.question, .help, .faq { --accent: 235,195,90; }
.abstract, .summary, .tldr, .info, .todo { --accent: 90,195,215; }
.example { --accent: 180,145,240; }
.quote, .cite { --accent: 170,170,170; }
"""


def render_html(source: str, base: Path) -> str:
    md = MarkdownIt('commonmark', {'html': False}).enable('table').enable('strikethrough')
    tokens = md.parse(source)
    stack = []
    for index, token in enumerate(tokens):
        if token.type == 'blockquote_open':
            inline = tokens[index + 2] if index + 2 < len(tokens) else None
            match = None
            if inline and inline.type == 'inline':
                match = re.match(r'^\[!([\w-]+)\][+-]?(?:[ \t]+([^\n]*))?(?:\n|$)', inline.content)
            stack.append(bool(match))
            if match:
                kind = match[1].lower()
                title = match[2] or kind.capitalize()
                token.tag = 'div'
                token.attrSet('class', f'callout {kind}')
                # Keep the first paragraph's body, but render the title separately.
                inline.content = inline.content[match.end():]
                inline.children = md.parseInline(inline.content)[0].children
                token.meta['title'] = md.renderInline(title)
        elif token.type == 'blockquote_close' and stack.pop():
            token.tag = 'div'
    output = []
    for token in tokens:
        output.append(token)
        if 'title' in token.meta:
            title = Token('html_block', '', 0)
            title.content = f'<div class="callout-title">{token.meta["title"]}</div>\n'
            output.append(title)
    body = md.renderer.render(output, md.options, {})
    csp = "default-src 'none'; img-src file: data:; style-src 'unsafe-inline'; font-src file: data:; base-uri file: data:"
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
            f'<base href="{html.escape(base.resolve().as_uri() + "/", quote=True)}">'
            f'<style>{STYLE}</style></head><body><main>{body}</main></body></html>')


def snapshot(document: Path, target: Path, width: int, boundaries_target: Path) -> None:
    # This worker runs on a private Xvfb display: no desktop window appears.
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gdk, GLib, Gtk, WebKit2

    window = Gtk.Window()
    window.set_default_size(width, 200)
    view = WebKit2.WebView()
    # The generated page has no executable Markdown HTML; CSP also blocks page scripts.
    view.get_settings().set_enable_javascript(True)
    color = Gdk.RGBA()
    color.parse('rgba(0,0,0,0)')
    view.set_background_color(color)
    window.add(view)
    failures = []

    def finish(webview, result, _data):
        try:
            surface = webview.get_snapshot_finish(result)
            surface.write_to_png(str(target))
        except Exception as error:
            failures.append(str(error))
        Gtk.main_quit()

    def capture():
        script = "JSON.stringify([...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p')].map(el => Math.round(el.getBoundingClientRect().top + window.scrollY)))"

        def got_boundaries(webview, result, _data):
            try:
                value = webview.evaluate_javascript_finish(result)
                boundaries_target.write_text(value.to_string(), encoding='utf-8')
                webview.get_snapshot(WebKit2.SnapshotRegion.FULL_DOCUMENT,
                                     WebKit2.SnapshotOptions.TRANSPARENT_BACKGROUND,
                                     None, finish, None)
            except Exception as error:
                failures.append(str(error))
                Gtk.main_quit()

        view.evaluate_javascript(script, -1, None, None, None, got_boundaries, None)
        return False

    def loaded(_view, event):
        if event == WebKit2.LoadEvent.FINISHED:
            # Allow the final layout/paint after resources finish loading.
            GLib.timeout_add(100, capture)

    def failed(_view, _event, _uri, error):
        failures.append(error.message)
        Gtk.main_quit()
        return True

    def timed_out():
        failures.append('Rendering timed out after 30 seconds')
        Gtk.main_quit()
        return False

    view.connect('load-changed', loaded)
    view.connect('load-failed', failed)
    GLib.timeout_add_seconds(30, timed_out)
    window.show_all()
    view.load_uri(document.as_uri())
    Gtk.main()
    window.destroy()
    if failures:
        raise RuntimeError('; '.join(failures))


def split_image(image: Path, directory: Path, max_height: int,
                row_height: int = 1, boundaries: list[int] | None = None) -> list[Path]:
    paths = []
    with Image.open(image) as source:
        row_height = max(1, row_height)
        max_height = max(row_height, max_height // row_height * row_height)
        cuts = sorted(set(boundaries or []))
        top = 0
        index = 0
        while top < source.height:
            eligible = [cut for cut in cuts if top < cut <= source.height
                        and math.ceil((cut - top) / row_height) * row_height <= max_height]
            end = max(eligible) if eligible else min(top + max_height, source.height)
            crop = source.crop((0, top, source.width, end))
            padded_height = math.ceil(crop.height / row_height) * row_height
            if padded_height != crop.height:
                padded = Image.new('RGBA', (source.width, padded_height))
                padded.paste(crop, (0, 0))
                crop = padded
            path = directory / f'strip-{index:05d}.png'
            crop.save(path)
            paths.append(path)
            top = end
            index += 1
    return paths


def terminal_size() -> tuple[int, int, int, int]:
    import fcntl
    import termios
    with open('/dev/tty', 'rb') as tty:
        rows, cols, width, height = struct.unpack('HHHH', fcntl.ioctl(tty, termios.TIOCGWINSZ, bytes(8)))
    if not all((rows, cols, width, height)):
        raise RuntimeError('Terminal did not report its pixel dimensions; use --output with --width to export instead')
    return rows, cols, width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path, help='Markdown file to render')
    parser.add_argument('--output', type=Path, help='Export numbered PNG strips to a directory instead of displaying')
    parser.add_argument('--width', type=int, default=900, help='Export width in pixels (default: 900)')
    parser.add_argument('--strip-height', type=int, default=800, help='Maximum export strip height (default: 800)')
    args = parser.parse_args()
    if args.width < 64 or args.strip_height < 1:
        parser.error('--width must be at least 64 and --strip-height must be positive')
    try:
        source = args.file.read_text(encoding='utf-8')
        if not shutil.which('xvfb-run'):
            raise RuntimeError('xvfb-run is required for windowless system WebKit rendering')
        if args.output:
            width, strip_height = args.width, args.strip_height
        else:
            if not shutil.which('kitten'):
                raise RuntimeError('Kitty\'s kitten executable is required')
            rows, cols, width, screen_height = terminal_size()
            # Whole terminal rows prevent rounding gaps between image placements.
            row_quantum = screen_height // math.gcd(screen_height, rows)
            strip_height = max(row_quantum, (screen_height // 2 // row_quantum) * row_quantum)
        with tempfile.TemporaryDirectory(prefix='mdview-') as temporary:
            root = Path(temporary)
            document = root / 'document.html'
            document.write_text(render_html(source, args.file.resolve().parent), encoding='utf-8')
            page = root / 'page.png'
            boundaries = root / 'boundaries.json'
            subprocess.run(['xvfb-run', '-a', sys.executable, str(Path(__file__).resolve()),
                            '--snapshot-worker', str(document), str(page), str(width), str(boundaries)],
                           check=True, timeout=40)
            block_boundaries = json.loads(boundaries.read_text(encoding='utf-8'))
            strips = split_image(page, root, strip_height, 1, block_boundaries)
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                for path in strips:
                    shutil.copyfile(path, args.output / path.name)
                print(f'Exported {len(strips)} strip(s) to {args.output}')
            else:
                # Stream transfer lets the temporary files be removed immediately.
                subprocess.run(['kitten', 'icat', '--align=left', '--background=none',
                                '--fit=none', '--transfer-mode=stream', '--stdin=no',
                                '--use-window-size', f'{cols},{rows},{width},{screen_height}',
                                *map(str, strips)], check=True)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'mdview: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--snapshot-worker':
        snapshot(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5]))
    else:
        sys.exit(main())
