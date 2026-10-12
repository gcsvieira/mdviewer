#!/usr/bin/env python3
"""Render Markdown through the system WebKitGTK engine and display it in Kitty."""
import argparse
import curses
import html
import json
import math
import re
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
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


def start_renderer_worker():
    if not shutil.which('xvfb-run'):
        raise RuntimeError('xvfb-run is required for windowless WebKit rendering')
    worker = subprocess.Popen(
        ['xvfb-run', '-a', sys.executable, str(Path(__file__).resolve()), '--renderer-worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
    )
    worker.responses = queue.Queue()
    threading.Thread(target=_read_worker_responses, args=(worker,), daemon=True).start()
    return worker


def _read_worker_responses(worker) -> None:
    for line in worker.stdout:
        worker.responses.put(line)
    worker.responses.put(None)


def request_render(worker, request: dict, timeout: int = 40) -> dict:
    if worker.poll() is not None:
        raise RuntimeError('WebKit renderer worker has stopped')
    worker.stdin.write(json.dumps(request) + '\n')
    worker.stdin.flush()
    try:
        line = worker.responses.get(timeout=timeout)
    except queue.Empty:
        worker.terminate()
        try:
            worker.wait(timeout=1)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
        raise RuntimeError(f'WebKit renderer timed out after {timeout} seconds')
    if not line:
        raise RuntimeError('WebKit renderer stopped before returning a result')
    return json.loads(line)


def renderer_worker() -> None:
    """Serve JSON-line Markdown render requests on one private Xvfb display."""
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gdk, GLib, Gtk, WebKit2

    window = Gtk.Window()
    window.set_default_size(900, 700)
    view = WebKit2.WebView()
    view.get_settings().set_enable_javascript(True)
    color = Gdk.RGBA()
    color.parse('rgba(0,0,0,0)')
    view.set_background_color(color)
    window.add(view)
    window.show_all()
    previous = None

    for line in sys.stdin:
        state = {'done': False, 'response': None, 'timer': 0}

        def finish(response):
            if state['done']:
                return
            state['done'] = True
            state['response'] = response
            if state['timer']:
                GLib.source_remove(state['timer'])
            Gtk.main_quit()

        try:
            request = json.loads(line)
            source = Path(request['path']).resolve()
            markdown = source.read_text(encoding='utf-8')
            width = int(request['width'])
            page_height = int(request['page_height'])
            row_height = int(request['row_height'])
            if width < 64 or page_height < 1 or row_height < 1:
                raise ValueError('width, page_height, and row_height must be positive')
            if previous is not None:
                previous.cleanup()
            previous = tempfile.TemporaryDirectory(prefix='mdview-worker-')
            root = Path(previous.name)
            document, page = root / 'document.html', root / 'page.png'
            boundaries_file = root / 'boundaries.json'
            document.write_text(render_html(markdown, source.parent), encoding='utf-8')
            window.resize(width, page_height)

            def on_snapshot(webview, result, _data):
                try:
                    surface = webview.get_snapshot_finish(result)
                    surface.write_to_png(str(page))
                    boundaries = json.loads(boundaries_file.read_text(encoding='utf-8'))
                    strips = split_image(page, root, page_height, row_height, boundaries)
                    finish({'ok': True, 'strips': [str(path) for path in strips]})
                except Exception as error:
                    finish({'ok': False, 'error': str(error)})

            def on_bounds(webview, result, _data):
                try:
                    value = webview.evaluate_javascript_finish(result)
                    boundaries_file.write_text(value.to_string(), encoding='utf-8')
                    webview.get_snapshot(WebKit2.SnapshotRegion.FULL_DOCUMENT,
                                         WebKit2.SnapshotOptions.TRANSPARENT_BACKGROUND,
                                         None, on_snapshot, None)
                except Exception as error:
                    finish({'ok': False, 'error': str(error)})

            def on_load(_view, event):
                if event == WebKit2.LoadEvent.FINISHED:
                    script = "JSON.stringify([...document.querySelectorAll('h1,h2,h3,h4,h5,h6,p')].map(el => Math.round(el.getBoundingClientRect().top + window.scrollY)))"
                    view.evaluate_javascript(script, -1, None, None, None, on_bounds, None)

            def on_failed(_view, _event, _uri, error):
                finish({'ok': False, 'error': error.message})
                return True

            view.connect('load-changed', on_load)
            view.connect('load-failed', on_failed)
            state['timer'] = GLib.timeout_add_seconds(
                35, lambda: (finish({'ok': False, 'error': 'Rendering timed out after 35 seconds'}), False)[1])
            view.load_uri(document.as_uri())
            Gtk.main()
            view.stop_loading()
            view.disconnect_by_func(on_load)
            view.disconnect_by_func(on_failed)
            print(json.dumps(state['response']), flush=True)
        except Exception as error:
            print(json.dumps({'ok': False, 'error': str(error)}), flush=True)

    if previous is not None:
        previous.cleanup()
    window.destroy()


def terminal_size() -> tuple[int, int, int, int]:
    import fcntl
    import termios
    with open('/dev/tty', 'rb') as tty:
        rows, cols, width, height = struct.unpack('HHHH', fcntl.ioctl(tty, termios.TIOCGWINSZ, bytes(8)))
    if not all((rows, cols, width, height)):
        raise RuntimeError('Terminal did not report its pixel dimensions; use --output with --width to export instead')
    return rows, cols, width, height


def markdown_files(directory: Path) -> list[Path]:
    return sorted((path for path in directory.iterdir()
                   if path.is_file() and path.suffix.lower() in {'.md', '.markdown'}),
                  key=lambda path: path.name.casefold())


def navigation_action(mode: str, key: str) -> str | None:
    if mode == 'picker':
        return {'j': 'down', 'k': 'up', '\n': 'open', '\r': 'open', 'ENTER': 'open', 'q': 'quit'}.get(key)
    return {'j': 'next', 'k': 'previous', 'q': 'back'}.get(key)


def move_selection(index: int, action: str, count: int) -> int:
    if count < 1:
        return 0
    if action == 'down':
        return min(index + 1, count - 1)
    if action == 'up':
        return max(index - 1, 0)
    return index


def clear_kitty_images() -> None:
    subprocess.run(['kitten', 'icat', '--clear'], check=True)


def restore_picker(screen) -> None:
    clear_kitty_images()
    screen.clear()
    screen.refresh()


def show_page(screen, image: Path, title: str, page: int, count: int, cols: int, rows: int) -> None:
    screen.erase()
    screen.addnstr(0, 0, f' {title}  page {page + 1}/{count}   j/k: page   q: files ', max(1, cols - 1))
    screen.refresh()
    subprocess.run([
        'kitten', 'icat', '--align=left', '--background=none', '--fit=none',
        '--transfer-mode=stream', '--stdin=no', '--z-index=-1',
        '--place', f'{cols}x{rows - 1}@0x1', str(image),
    ], check=True)


def picker(screen, worker, rows: int, cols: int, width: int, screen_height: int) -> None:
    files = markdown_files(Path.cwd())
    selected = 0
    error = None
    row_height = max(1, screen_height // rows)
    page_height = row_height * max(1, rows - 1)
    mode, pages, current_page = 'picker', [], 0

    while True:
        if mode == 'picker':
            screen.erase()
            screen.addnstr(0, 0, ' mdview   j/k: move   Enter: open   q: quit ', max(1, cols - 1))
            available = max(0, rows - 2)
            first = max(0, min(selected - available + 1, len(files) - available))
            for row, path in enumerate(files[first:first + available], start=1):
                attr = curses.A_REVERSE if first + row - 1 == selected else 0
                screen.addnstr(row, 0, path.name, max(1, cols - 1), attr)
            if not files:
                screen.addnstr(2, 0, 'No Markdown files in this directory.', max(1, cols - 1))
            if error:
                screen.addnstr(rows - 1, 0, error, max(1, cols - 1))
            screen.refresh()
            key = screen.getch()
            key_text = 'ENTER' if key in (10, 13, curses.KEY_ENTER) else chr(key) if 0 <= key < 256 else ''
            action = navigation_action('picker', key_text)
            if action == 'quit':
                return
            if action in ('up', 'down'):
                selected = move_selection(selected, action, len(files))
            elif action == 'open' and files:
                try:
                    response = request_render(worker, {
                        'path': str(files[selected].resolve()), 'width': width,
                        'page_height': page_height, 'row_height': row_height,
                    })
                    if not response.get('ok'):
                        raise RuntimeError(response.get('error', 'Rendering failed'))
                    pages = [Path(path) for path in response['strips']]
                    current_page = 0
                    mode, error = 'preview', None
                except (OSError, RuntimeError, ValueError, KeyError) as exception:
                    error = str(exception)
        else:
            show_page(screen, pages[current_page], files[selected].name, current_page, len(pages), cols, rows)
            key = screen.getch()
            key_text = chr(key) if 0 <= key < 256 else ''
            action = navigation_action('preview', key_text)
            if action == 'back':
                restore_picker(screen)
                mode = 'picker'
            elif action == 'next' and current_page + 1 < len(pages):
                clear_kitty_images()
                current_page += 1
            elif action == 'previous' and current_page > 0:
                clear_kitty_images()
                current_page -= 1


def close_renderer_worker(worker) -> None:
    if worker.poll() is None:
        worker.stdin.close()
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker.terminate()
            worker.wait(timeout=5)
    worker.stdout.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', type=Path, help='Markdown file to render; omit for the picker')
    parser.add_argument('--output', type=Path, help='Export numbered PNG strips to a directory instead of displaying')
    parser.add_argument('--width', type=int, default=900, help='Export width in pixels (default: 900)')
    parser.add_argument('--strip-height', type=int, default=800, help='Maximum export strip height (default: 800)')
    args = parser.parse_args()
    if args.width < 64 or args.strip_height < 1:
        parser.error('--width must be at least 64 and --strip-height must be positive')
    if args.output and not args.file:
        parser.error('--output requires a Markdown file')
    if not args.file and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        parser.error('the file picker requires an interactive terminal')
    try:
        if args.file:
            if args.output:
                width, page_height, row_height = args.width, args.strip_height, 1
            else:
                if not shutil.which('kitten'):
                    raise RuntimeError("Kitty's kitten executable is required")
                rows, cols, width, screen_height = terminal_size()
                row_height = max(1, screen_height // rows)
                page_height = max(row_height, (screen_height // 2 // row_height) * row_height)
        else:
            if not shutil.which('kitten'):
                raise RuntimeError("Kitty's kitten executable is required")
            rows, cols, width, screen_height = terminal_size()
            row_height = max(1, screen_height // rows)
            page_height = row_height * max(1, rows - 1)

        worker = start_renderer_worker()
        try:
            if args.file:
                response = request_render(worker, {
                    'path': str(args.file.resolve()), 'width': width,
                    'page_height': page_height, 'row_height': row_height,
                })
                if not response.get('ok'):
                    raise RuntimeError(response.get('error', 'Rendering failed'))
                strips = [Path(path) for path in response['strips']]
                if args.output:
                    args.output.mkdir(parents=True, exist_ok=True)
                    for index, path in enumerate(strips):
                        shutil.copyfile(path, args.output / f'strip-{index:05d}.png')
                    print(f'Exported {len(strips)} strip(s) to {args.output}')
                else:
                    subprocess.run([
                        'kitten', 'icat', '--align=left', '--background=none',
                        '--fit=none', '--transfer-mode=stream', '--stdin=no',
                        '--use-window-size', f'{cols},{rows},{width},{screen_height}',
                        *map(str, strips),
                    ], check=True)
            else:
                curses.wrapper(lambda screen: picker(screen, worker, rows, cols, width, screen_height))
        finally:
            close_renderer_worker(worker)
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'mdview: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--renderer-worker':
        renderer_worker()
    else:
        sys.exit(main())
