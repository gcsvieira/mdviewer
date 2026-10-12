#!/usr/bin/env python3
"""Render Markdown through the system WebKitGTK engine and display it in Kitty."""
import argparse
import base64
import curses
import html
import json
import math
import os
import re
import queue
import shlex
import shutil
import signal
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
from mdview_settings import OPTIONS, Settings, load_settings, save_settings


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


def render_html(source: str, base: Path, element_color: str = 'white') -> str:
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
    style = STYLE
    if element_color == 'black':
        style += '''
body, h1, h2, h3, h4, h5, h6, blockquote, .callout-title { color: #171717; }
a { color: #49318a; }
th, td { border-color: rgba(0,0,0,.3); }
hr { border-top-color: rgba(0,0,0,.3); }
code, pre, th { background: rgba(0,0,0,.08); }
pre code { background: transparent; }
'''
    return ('<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
            f'<base href="{html.escape(base.resolve().as_uri() + "/", quote=True)}">'
            f'<style>{style}</style></head><body><main>{body}</main></body></html>')


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
    renderer_env = os.environ.copy()
    renderer_env['GDK_BACKEND'] = 'x11'
    renderer_env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    renderer_env.pop('WAYLAND_DISPLAY', None)
    # Some xvfb-run versions merge stderr into stdout. Keep JSON on its own pipe.
    response_read, response_write = os.pipe()
    renderer_env['MDVIEW_RESPONSE_FD'] = str(response_write)
    try:
        worker = subprocess.Popen(
            ['xvfb-run', '-a', sys.executable, str(Path(__file__).resolve()), '--renderer-worker'],
            stdin=subprocess.PIPE, stdout=sys.stderr, text=True, bufsize=1,
            env=renderer_env, pass_fds=(response_write,), start_new_session=True,
        )
    except Exception:
        os.close(response_read)
        raise
    finally:
        os.close(response_write)
    worker.stdout = os.fdopen(response_read, 'r')
    worker.responses = queue.Queue()
    worker.response_reader = threading.Thread(target=_read_worker_responses, args=(worker,), daemon=True)
    worker.response_reader.start()
    return worker


def _read_worker_responses(worker) -> None:
    for line in worker.stdout:
        worker.responses.put(line)
    worker.responses.put(None)


class QuitViewer(Exception):
    """A quit request while waiting for a render."""


def stop_renderer_worker(worker) -> None:
    try:
        isolated = os.getpgid(worker.pid) == worker.pid
        if isolated:
            os.killpg(worker.pid, signal.SIGTERM)
        else:
            worker.terminate()
        try:
            worker.wait(timeout=1)
        except subprocess.TimeoutExpired:
            if isolated:
                os.killpg(worker.pid, signal.SIGKILL)
            else:
                worker.kill()
            worker.wait()
    except ProcessLookupError:
        worker.wait()


def request_render(worker, request: dict, timeout: int = 40, progress=None) -> dict:
    if worker.poll() is not None:
        raise RuntimeError('WebKit renderer worker has stopped')
    worker.stdin.write(json.dumps(request) + '\n')
    worker.stdin.flush()
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            stop_renderer_worker(worker)
            raise RuntimeError(f'WebKit renderer timed out after {timeout} seconds')
        try:
            line = worker.responses.get(timeout=min(.1, remaining) if progress else remaining)
            break
        except queue.Empty:
            if progress:
                try:
                    progress()
                except QuitViewer:
                    stop_renderer_worker(worker)
                    raise
    if not line:
        raise RuntimeError('WebKit renderer stopped before returning a result')
    return json.loads(line)


def renderer_worker() -> None:
    """Serve JSON-line Markdown render requests on one private Xvfb display."""
    protocol_output = os.fdopen(int(os.environ.pop('MDVIEW_RESPONSE_FD')), 'w', buffering=1)
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
            document.write_text(render_html(markdown, source.parent, request.get('element_color', 'white')), encoding='utf-8')
            window.resize(width, page_height)

            def on_snapshot(webview, result, _data):
                try:
                    surface = webview.get_snapshot_finish(result)
                    surface.write_to_png(str(page))
                    boundaries = json.loads(boundaries_file.read_text(encoding='utf-8'))
                    strips = split_image(page, root, page_height, row_height, boundaries)
                    finish({'ok': True, 'image': str(page), 'boundaries': boundaries,
                            'strips': [str(path) for path in strips]})
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
            print(json.dumps(state['response']), file=protocol_output, flush=True)
        except Exception as error:
            print(json.dumps({'ok': False, 'error': str(error)}), file=protocol_output, flush=True)

    if previous is not None:
        previous.cleanup()
    window.destroy()
    protocol_output.close()


def terminal_size() -> tuple[int, int, int, int]:
    import fcntl
    import termios
    with open('/dev/tty', 'rb') as tty:
        rows, cols, width, height = struct.unpack('HHHH', fcntl.ioctl(tty, termios.TIOCGWINSZ, bytes(8)))
    if not all((rows, cols, width, height)):
        raise RuntimeError('Terminal did not report its pixel dimensions; use --output with --width to export instead')
    return rows, cols, width, height


def markdown_files(directory: Path) -> list[Path]:
    return sorted((path for path in directory.iterdir() if not path.name.startswith('.')
                   and path.is_file() and path.suffix.lower() in {'.md', '.markdown'}),
                  key=lambda path: path.name.casefold())


def directory_entries(directory: Path) -> list[Path]:
    folders = sorted((path for path in directory.iterdir() if path.is_dir()
                      and not path.name.startswith('.') and path.name != 'node_modules'),
                     key=lambda path: path.name.casefold())
    return folders + markdown_files(directory)


def key_text(key: int) -> str:
    special = {curses.KEY_UP: 'UP', curses.KEY_DOWN: 'DOWN',
               curses.KEY_LEFT: 'LEFT', curses.KEY_RIGHT: 'RIGHT',
               curses.KEY_HOME: 'HOME', curses.KEY_END: 'END', curses.KEY_ENTER: 'ENTER'}
    return special.get(key, chr(key) if 0 <= key < 256 else '')


def navigation_action(mode: str, key: str, vim_mode: bool = False) -> str | None:
    if key == 'q':
        return 'quit'
    if key == 's' and mode == 'picker':
        return 'settings'
    if mode == 'settings' and key in ('s', '\x1b'):
        return 'back'
    if key == 'e' and mode != 'settings':
        return 'edit'
    keys = ({'k': 'up', 'j': 'down', 'h': 'back', 'l': 'open', 'gg': 'top', 'G': 'bottom'}
            if vim_mode else {'UP': 'up', 'DOWN': 'down', 'LEFT': 'back', 'RIGHT': 'open',
                              'HOME': 'top', 'END': 'bottom'})
    action = keys.get(key)
    if mode == 'preview':
        return {'up': 'previous', 'down': 'next', 'back': 'back',
                'top': 'top', 'bottom': 'bottom'}.get(action)
    return action


def navigation_input(mode: str, key: str, pending_g: bool, vim_mode: bool = False) -> tuple[str | None, bool]:
    if key == 'g' and vim_mode:
        return (navigation_action(mode, 'gg', True), False) if pending_g else (None, True)
    return navigation_action(mode, key, vim_mode), False


def editor_command(path: Path) -> list[str]:
    command = next((os.environ[name].strip() for name in ('EDITOR', 'VISUAL')
                    if os.environ.get(name, '').strip()), 'vi')
    arguments = shlex.split(command)
    if not arguments or not arguments[0]:
        raise ValueError('Editor command is empty')
    return [*arguments, str(path.resolve())]


def edit_file(screen, path: Path) -> str | None:
    try:
        command = editor_command(path)
    except ValueError as exception:
        return f'Invalid editor command: {exception}'
    clear_kitty_images()
    curses.def_prog_mode()
    curses.endwin()
    # Let the editor handle Ctrl+C while the viewer waits. Caught signal
    # handlers revert to defaults when the editor executable starts.
    previous_interrupt = signal.signal(signal.SIGINT, lambda _signal, _frame: None)
    error = None
    try:
        result = subprocess.run(command)
        if result.returncode:
            error = f'Editor exited with status {result.returncode}'
    except OSError as exception:
        error = f'Could not open editor: {exception}'
    finally:
        signal.signal(signal.SIGINT, previous_interrupt)
        curses.reset_prog_mode()
        rows, cols, _, _ = terminal_size()
        if (rows, cols) != screen.getmaxyx():
            curses.resizeterm(rows, cols)
        screen.keypad(True)
        curses.curs_set(0)
        screen.clear()
        screen.refresh()
    return error


def draw_loading(screen, path: Path, frame: int) -> None:
    rows, cols = screen.getmaxyx()
    screen.erase()
    put_text(screen, max(0, rows // 2 - 1), 1, f'Opening {path.name}…')
    bar = [' '] * 20
    for index in range(4):
        bar[(frame + index) % len(bar)] = '━'
    put_text(screen, rows // 2, 1, '[' + ''.join(bar) + ']')
    put_text(screen, rows - 1, 0, ' q quit ', curses.A_DIM)
    screen.refresh()


def load_document(worker, path: Path, width: int, page_height: int, row_height: int,
                  settings: Settings | None = None, screen=None) -> tuple[Image.Image, Path, list[int]]:
    settings = settings or Settings()
    progress = None
    if screen is not None:
        clear_kitty_images()
        screen.timeout(0)
        draw_loading(screen, path, 0)
        frame = 0

        def progress():
            nonlocal frame
            frame += 1
            draw_loading(screen, path, frame)
            if screen.getch() == ord('q'):
                raise QuitViewer()
    try:
        response = request_render(worker, {
            'path': str(path.resolve()), 'width': width, 'element_color': settings.element_color,
            'page_height': page_height, 'row_height': row_height,
        }, progress=progress)
    finally:
        if screen is not None:
            screen.timeout(500)
    if not response.get('ok'):
        raise RuntimeError(response.get('error', 'Rendering failed'))
    image_path = Path(response['image'])
    with Image.open(image_path) as source:
        image = source.convert('RGBA')
    return image, image_path.parent / 'viewport.png', response.get('boundaries', [])


def move_selection(index: int, action: str, count: int) -> int:
    if count < 1:
        return 0
    if action in ('top', 'bottom'):
        return 0 if action == 'top' else count - 1
    if action == 'down':
        return min(index + 1, count - 1)
    if action == 'up':
        return max(index - 1, 0)
    return index


def clear_kitty_images() -> None:
    sys.stdout.write('\x1b_Ga=d,d=A,q=2\x1b\\')
    sys.stdout.flush()


def display_kitty_image(image: Path) -> None:
    data = base64.b64encode(image.read_bytes()).decode('ascii')
    for start in range(0, len(data), 4096):
        chunk = data[start:start + 4096]
        more = int(start + 4096 < len(data))
        params = 'a=T,f=100,t=d,q=2,z=1,C=1,' if start == 0 else ''
        sys.stdout.write(f'\x1b_G{params}m={more};{chunk}\x1b\\')
    sys.stdout.flush()


def restore_picker(screen) -> None:
    clear_kitty_images()
    screen.clear()
    screen.refresh()


def scroll_offset(offset: int, action: str, height: int, viewport_height: int, row_height: int) -> int:
    if action in ('top', 'bottom'):
        return 0 if action == 'top' else max(0, height - viewport_height)
    delta = row_height if action == 'next' else -row_height
    return max(0, min(offset + delta, max(0, height - viewport_height)))


def percentage_offset(percent: int, height: int, viewport_height: int) -> int:
    if not 0 <= percent <= 100:
        raise ValueError('Percentage must be between 0 and 100')
    return round(max(0, height - viewport_height) * percent / 100)


def page_offsets(height: int, viewport_height: int, row_height: int, boundaries: list[int]) -> list[int]:
    tops = [0]
    boundaries = sorted(set(boundaries))
    while height - tops[-1] > viewport_height:
        limit = tops[-1] + viewport_height
        candidates = [top for top in boundaries if tops[-1] < top <= limit]
        end = max(candidates) if candidates else max(tops[-1] + 1, limit // row_height * row_height)
        tops.append(end)
    return tops


def page_for_percentage(percent: int, pages: list[int]) -> int:
    if not 0 <= percent <= 100:
        raise ValueError('Percentage must be between 0 and 100')
    return round((len(pages) - 1) * percent / 100)


def crop_viewport(image: Image.Image, offset: int, height: int) -> Image.Image:
    return image.crop((0, offset, image.width, min(image.height, offset + height)))


def modified_ago(path: Path) -> str:
    try:
        seconds = max(0, int(time.time() - path.stat().st_mtime))
    except OSError:
        return 'unavailable'
    for unit, size in (('day', 86400), ('hour', 3600), ('minute', 60)):
        if seconds >= size:
            count = seconds // size
            return f'{count} {unit}{"s" if count != 1 else ""} ago'
    return 'just now'


def put_text(screen, row, column, text, attr=0):
    rows, cols = screen.getmaxyx()
    if 0 <= row < rows and 0 <= column < cols - 1:
        try:
            screen.addnstr(row, column, text, cols - column - 1, attr)
        except curses.error:
            # A resize can arrive between checking the bounds and writing.
            pass


def draw_picker(screen, files, selected, root, rows, cols, error, accent, badge, settings=None):
    settings = settings or Settings()
    muted = 0 if settings.element_color == 'black' else curses.A_DIM
    screen.erase()

    def put(row, column, text, attr=0):
        put_text(screen, row, column, text, attr)

    left = 3 if cols > 12 else 1
    put(1, left, ' MDVIEW ', badge | curses.A_BOLD)
    location = str(root)
    available_width = max(1, cols - left - 1)
    if len(location) > available_width:
        location = '…' + location[-max(1, available_width - 1):]
    put(3, left, location, muted)
    start, spacing = (5, 3) if rows >= 12 else (3, 2)
    available = max(1, (rows - 2 - start) // spacing)
    first = max(0, selected - available + 1)
    for index in range(first, min(len(files), first + available)):
        row = start + (index - first) * spacing
        active = index == selected
        attr = accent | curses.A_BOLD if active else 0
        if active:
            put(row, left - 2, '│', accent)
            put(row + 1, left - 2, '│', accent)
        put(row, left, files[index].name + ('/' if files[index].is_dir() else ''), attr)
        put(row + 1, left, modified_ago(files[index]), accent if active else muted)
    if not files:
        put(start, left, 'No folders or Markdown files found.', muted)
    keys = 'j/k move · gg/G · l open · h parent' if settings.vim_mode else '↑/↓ move · Home/End · → open · ← parent'
    put(rows - 2, left, error or f'{keys} · e edit · s settings · q quit', muted)
    screen.refresh()


def show_viewport(screen, image: Path, title: str, offset: int, maximum: int, cols: int, rows: int,
                  error: str | None = None, settings=None, page_index=None, page_count=None) -> None:
    settings = settings or Settings()
    muted = 0 if settings.element_color == 'black' else curses.A_DIM
    screen.erase()
    put_text(screen, 0, 0, f' {title} ', muted)
    percent = round(offset / maximum * 100) if maximum else 100
    page_label = ''
    if page_index is not None:
        percent = round(page_index / (page_count - 1) * 100) if page_count > 1 else 100
        page_label = f'page {page_index + 1}/{page_count} · '
    motion = 'page' if settings.file_navigation_style == 'paginated' else 'scroll'
    keys = f'j/k {motion} · gg/G · h files' if settings.vim_mode else f'↑/↓ {motion} · Home/End · ← files'
    put_text(screen, rows - 1, 0,
             error or f' {keys} · e edit · q quit   {page_label}{percent}% ', muted)
    if rows < 3:
        screen.refresh()
        return
    try:
        screen.move(1, 0)
    except curses.error:
        return
    screen.refresh()
    display_kitty_image(image)


def apply_palette(screen, settings: Settings) -> None:
    if curses.has_colors():
        foreground = curses.COLOR_BLACK if settings.element_color == 'black' else curses.COLOR_WHITE
        magenta = curses.COLOR_MAGENTA if settings.element_color == 'black' or curses.COLORS < 256 else 213
        curses.init_pair(1, magenta, -1)
        curses.init_pair(3, foreground, -1)
        screen.bkgd(' ', curses.color_pair(3))


def draw_settings(screen, settings, selected, error, accent, badge):
    muted = 0 if settings.element_color == 'black' else curses.A_DIM
    rows, cols = screen.getmaxyx()
    screen.erase()
    put_text(screen, 0, 1, ' SETTINGS ', badge | curses.A_BOLD)
    start, spacing = (3, 2) if rows >= 12 else (2, 1)
    for index, (name, _) in enumerate(OPTIONS):
        value = getattr(settings, name.replace('-', '_'))
        value = ('on' if value else 'off') if isinstance(value, bool) else value
        attr = accent | curses.A_BOLD if index == selected else 0
        put_text(screen, start + index * spacing, 1, f'{"›" if index == selected else " "} {name}: {value}', attr)
    keys = 'j/k select · l change · h back' if settings.vim_mode else '↑/↓ select · → change · ← back'
    put_text(screen, rows - 1, 0, error or f' {keys} · s/Esc back · q quit ', muted)
    screen.refresh()


def position_preview(image, boundaries, page_height, row_height, settings, offset):
    pages = page_offsets(image.height, page_height, row_height, boundaries)
    page_index = min(range(len(pages)), key=lambda index: abs(pages[index] - offset))
    if settings.file_navigation_style == 'paginated':
        offset = pages[page_index]
    else:
        offset = min(offset, max(0, image.height - page_height))
    return pages, page_index, offset


def picker(screen, worker, rows: int, cols: int, width: int, screen_height: int,
           accent: int = 0, badge: int = curses.A_REVERSE, settings: Settings | None = None) -> None:
    settings = settings or Settings()
    root = directory = Path.cwd()
    files = directory_entries(directory)
    selected, settings_selected = 0, 0
    remembered = {}
    error = None
    row_height = max(1, screen_height // rows)
    page_height = row_height * max(1, rows - 2)
    mode, image, offset, redraw = 'picker', None, 0, True
    boundaries, pages, page_index = [], [0], 0
    pending_g, pending_percentage = False, ''
    screen.timeout(500)

    while True:
        current_rows, current_cols = screen.getmaxyx()
        if (current_rows, current_cols) != (rows, cols):
            rows, cols = current_rows, current_cols
            page_height = row_height * max(1, rows - 2)
            if image is not None:
                pages, page_index, offset = position_preview(image, boundaries, page_height,
                                                            row_height, settings, offset)
            redraw = True
        if mode == 'settings':
            draw_settings(screen, settings, settings_selected, error, accent, badge)
            key = screen.getch()
            if key == -1:
                continue
            text = key_text(key)
            action, pending_g = navigation_input(mode, text, pending_g, settings.vim_mode)
            if action == 'quit':
                return
            if action == 'back':
                mode, error, pending_g = 'picker', None, False
            elif action in ('up', 'down', 'top', 'bottom'):
                settings_selected = move_selection(settings_selected, action, len(OPTIONS))
            elif action == 'open' or text == ' ':
                name, choices = OPTIONS[settings_selected]
                attribute = name.replace('-', '_')
                current = getattr(settings, attribute)
                setattr(settings, attribute, choices[(choices.index(current) + 1) % len(choices)])
                pending_g = False
                apply_palette(screen, settings)
                try:
                    save_settings(settings)
                    error = None
                except OSError as exception:
                    error = f'Could not save settings: {exception}'
            continue
        if mode == 'picker':
            old_path = files[selected] if files else None
            try:
                refreshed = directory_entries(directory)
                selected = refreshed.index(old_path) if old_path in refreshed else min(selected, max(0, len(refreshed) - 1))
                files = refreshed
            except OSError as exception:
                error = str(exception)
            draw_picker(screen, files, selected, directory, rows, cols, error, accent, badge, settings)
            key = screen.getch()
            if key == -1:
                continue
            action, pending_g = navigation_input(mode, key_text(key), pending_g, settings.vim_mode)
            if action == 'quit':
                return
            if action == 'settings':
                mode, error, pending_g = 'settings', None, False
            elif action in ('up', 'down', 'top', 'bottom'):
                selected = move_selection(selected, action, len(files))
            elif action == 'back' and directory != root:
                try:
                    refreshed = directory_entries(directory.parent)
                    remembered[directory] = files[selected] if files else None
                    old_directory, directory = directory, directory.parent
                    files = refreshed
                    selected = files.index(old_directory) if old_directory in files else 0
                    error = None
                except OSError as exception:
                    error = str(exception)
            elif action == 'open' and files:
                path = files[selected]
                try:
                    if path.is_dir():
                        refreshed = directory_entries(path)
                        remembered[directory] = path
                        directory, files = path, refreshed
                        remembered_path = remembered.get(directory)
                        selected = files.index(remembered_path) if remembered_path in files else 0
                        error = None
                    else:
                        image, viewport, boundaries = load_document(worker, path, width, page_height,
                                                                    row_height, settings, screen)
                        pages, page_index, offset = position_preview(image, boundaries, page_height,
                                                                    row_height, settings, 0)
                        redraw, mode, error = True, 'preview', None
                except QuitViewer:
                    return
                except (OSError, RuntimeError, ValueError, KeyError) as exception:
                    error = str(exception)
        else:
            paginated = settings.file_navigation_style == 'paginated'
            if redraw:
                height = (pages[page_index + 1] - offset
                          if paginated and page_index + 1 < len(pages) else page_height)
                crop_viewport(image, offset, height).save(viewport)
                clear_kitty_images()
                show_viewport(screen, viewport, str(files[selected].relative_to(root)), offset,
                              max(0, image.height - page_height), cols, rows, error, settings,
                              page_index if paginated else None, len(pages) if paginated else None)
                redraw = False
            key = screen.getch()
            if key == -1:
                continue
            text = key_text(key)
            digit = bool(text) and text in '0123456789'
            if digit or (pending_percentage and key in (curses.KEY_BACKSPACE, 8, 127)):
                pending_percentage = pending_percentage + text if digit else pending_percentage[:-1]
                pending_g, error = False, None
                if pending_percentage:
                    terminator = 'G' if settings.vim_mode else 'Enter'
                    hint = f' Jump to: {pending_percentage}% · {terminator} confirm · Esc cancel '
                    put_text(screen, rows - 1, 0, hint.ljust(max(1, cols - 1)), curses.A_DIM)
                    screen.refresh()
                else:
                    redraw = True
                continue
            confirm = text == 'G' if settings.vim_mode else text in ('\n', '\r', 'ENTER')
            if pending_percentage and confirm:
                try:
                    percent = int(pending_percentage)
                    if paginated:
                        page_index = page_for_percentage(percent, pages)
                        offset = pages[page_index]
                    else:
                        offset = percentage_offset(percent, image.height, page_height)
                    error = None
                except ValueError:
                    error = 'Percentage must be between 0 and 100'
                pending_percentage, pending_g, redraw = '', False, True
                continue
            if pending_percentage:
                pending_percentage, error, redraw = '', None, True
            if key == 27:
                pending_g, error, redraw = False, None, True
                continue
            action, pending_g = navigation_input(mode, text, pending_g, settings.vim_mode)
            if action == 'quit':
                clear_kitty_images()
                return
            if action == 'back':
                restore_picker(screen)
                mode = 'picker'
            elif action in ('next', 'previous', 'top', 'bottom'):
                if paginated:
                    direction = {'next': 'down', 'previous': 'up'}.get(action, action)
                    page_index = move_selection(page_index, direction, len(pages))
                    new_offset = pages[page_index]
                else:
                    new_offset = scroll_offset(offset, action, image.height, page_height, row_height)
                redraw = redraw or new_offset != offset
                offset = new_offset
        if action == 'edit' and files and files[selected].is_file():
            path = files[selected]
            error = edit_file(screen, path)
            pending_g, pending_percentage = False, ''
            try:
                files = directory_entries(directory)
            except OSError as exception:
                error = str(exception)
                files = []
            selected = files.index(path) if path in files else min(selected, max(0, len(files) - 1))
            rows, cols = screen.getmaxyx()
            page_height = row_height * max(1, rows - 2)
            if mode == 'preview':
                try:
                    if not path.is_file():
                        raise RuntimeError(f'File no longer exists: {path.name}')
                    image, viewport, boundaries = load_document(worker, path, width, page_height,
                                                                row_height, settings, screen)
                    pages, page_index, offset = position_preview(image, boundaries, page_height,
                                                                row_height, settings, offset)
                    redraw = True
                except QuitViewer:
                    return
                except (OSError, RuntimeError, ValueError, KeyError) as exception:
                    error = f'{error}; {exception}' if error else str(exception)
                    restore_picker(screen)
                    mode = 'picker'


def run_picker(screen, worker, rows, cols, width, screen_height, settings=None):
    settings = settings or load_settings()
    curses.curs_set(0)
    accent, badge = 0, curses.A_REVERSE
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        magenta = 213 if curses.COLORS >= 256 else curses.COLOR_MAGENTA
        curses.init_pair(1, magenta, -1)
        curses.init_pair(2, curses.COLOR_WHITE, magenta)
        accent, badge = curses.color_pair(1), curses.color_pair(2)
    apply_palette(screen, settings)
    picker(screen, worker, rows, cols, width, screen_height, accent, badge, settings)


def close_renderer_worker(worker) -> None:
    if not worker.stdin.closed:
        worker.stdin.close()
    if worker.poll() is None:
        try:
            worker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            stop_renderer_worker(worker)
    reader = getattr(worker, 'response_reader', None)
    if reader is not None:
        reader.join(timeout=1)
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
        settings = load_settings()
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
                    'element_color': settings.element_color,
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
                curses.wrapper(lambda screen: run_picker(screen, worker, rows, cols, width, screen_height, settings))
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
