import tempfile
import base64
import io
import queue
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from PIL import Image
import mdview


def start_worker():
    start = getattr(mdview, 'start_renderer_worker', None)
    if start is None:
        raise AssertionError('mdview must provide a persistent WebKit renderer worker')
    return start()


def render_request(worker, path):
    request = {'path': str(path), 'width': 640, 'page_height': 500, 'row_height': 20}
    return mdview.request_render(worker, request)


class RenderingTests(unittest.TestCase):
    def test_callouts_and_code(self):
        html = mdview.render_html('> [!WARNING]- Custom **title**\n> Body\n\n```\n> [!NOTE] literal\n```\n', Path('/tmp'))
        self.assertIn('callout warning', html)
        self.assertIn('Custom <strong>title</strong>', html)
        self.assertIn('<p>Body</p>', html)
        self.assertIn('&gt; [!NOTE] literal', html)
        self.assertNotIn('[!WARNING]', html)

    def test_nested_callout_and_table(self):
        html = mdview.render_html('> [!NOTE]\n> Outer\n>\n> > [!TIP]\n> > Inner\n\n| A | B |\n|---|---|\n| 1 | 2 |', Path('/tmp'))
        self.assertIn('callout note', html)
        self.assertIn('callout tip', html)
        self.assertIn('<table>', html)

    def test_strips_preserve_pixels_and_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Image.new('RGBA', (123, 257))
            for y in range(original.height):
                for x in range(original.width):
                    original.putpixel((x, y), (x, y % 256, 80, 150))
            original.save(root / 'page.png')
            strips = mdview.split_image(root / 'page.png', root, 96)
            sizes = []
            for path in strips:
                with Image.open(path) as strip:
                    sizes.append(strip.size)
            self.assertEqual(sizes, [(123, 96), (123, 96), (123, 65)])
            joined = Image.new('RGBA', original.size)
            top = 0
            for path in strips:
                with Image.open(path) as strip:
                    joined.paste(strip, (0, top))
                    top += strip.height
            self.assertEqual(joined.tobytes(), original.tobytes())

    def test_strips_break_before_nearby_markdown_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Image.new('RGBA', (8, 250), (40, 80, 120, 255))
            original.save(root / 'page.png')
            strips = mdview.split_image(root / 'page.png', root, 100, 10, [80, 160])
            with Image.open(strips[0]) as first:
                self.assertEqual(first.size, (8, 80))
            with Image.open(strips[1]) as second:
                self.assertEqual(second.getpixel((0, 0)), (40, 80, 120, 255))

    def test_tall_blocks_fall_back_to_row_aligned_strips(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            Image.new('RGBA', (8, 250), (40, 80, 120, 255)).save(root / 'page.png')
            strips = mdview.split_image(root / 'page.png', root, 100, 10, [])
            with Image.open(strips[0]) as first:
                self.assertEqual(first.size, (8, 100))
            with Image.open(strips[1]) as second:
                self.assertEqual(second.size, (8, 100))

    def test_block_boundary_padding_keeps_every_source_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = Image.new('RGBA', (8, 97))
            for y in range(original.height):
                for x in range(original.width):
                    original.putpixel((x, y), (x, y, 50, 255))
            original.save(root / 'page.png')
            strips = mdview.split_image(root / 'page.png', root, 60, 10, [33])
            rows = []
            for path in strips:
                with Image.open(path) as strip:
                    self.assertEqual(strip.height % 10, 0)
                    rows.extend(strip.getpixel((0, y)) for y in range(strip.height))
            visible = [pixel for pixel in rows if pixel[3]]
            expected = [original.getpixel((0, y)) for y in range(original.height)]
            self.assertEqual(visible, expected)


class RendererWorkerTests(unittest.TestCase):
    def test_renderer_survives_foreground_interrupt_during_edit(self):
        script = '''
import os, signal, tempfile, time
from pathlib import Path
import mdview
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'note.md'
    path.write_text('# Signal test')
    worker = mdview.start_renderer_worker()
    request = {'path': str(path), 'width': 640, 'page_height': 400, 'row_height': 20}
    try:
        assert mdview.request_render(worker, request)['ok']
        signal.signal(signal.SIGINT, lambda *_: None)
        os.killpg(os.getpgrp(), signal.SIGINT)
        time.sleep(.2)
        assert mdview.request_render(worker, request)['ok']
    finally:
        mdview.close_renderer_worker(worker)
'''
        result = subprocess.run([sys.executable, '-c', script],
                                cwd=Path(mdview.__file__).parent, start_new_session=True,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_worker_response_respects_timeout_and_stops_worker(self):
        worker = subprocess.Popen(
            [sys.executable, '-c', "import sys,time; sys.stdin.readline(); sys.stdout.write('{\\\"ok\\\":'); sys.stdout.flush(); time.sleep(5)"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )
        worker.responses = queue.Queue()
        threading.Thread(target=mdview._read_worker_responses, args=(worker,), daemon=True).start()
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                mdview.request_render(worker, {'path': 'unused'}, timeout=0.1)
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertIsNotNone(worker.poll())
        finally:
            if worker.poll() is None:
                worker.kill()
            worker.wait()
            worker.stdin.close()
            worker.stdout.close()

    def test_one_worker_renders_multiple_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / 'first.md'
            second = root / 'second.md'
            first.write_text('# First file\n\nFirst body.', encoding='utf-8')
            second.write_text('# Second file\n\nSecond body.', encoding='utf-8')
            worker = start_worker()
            try:
                self.assertIsNone(worker.poll(), 'renderer worker must remain alive for requests')
                first_result = render_request(worker, first)
                self.assertTrue(first_result['ok'], first_result)
                self.assertTrue(Path(first_result['strips'][0]).is_file())
                second_result = render_request(worker, second)
                self.assertTrue(second_result['ok'], second_result)
                self.assertTrue(Path(second_result['strips'][0]).is_file())
                self.assertIsNone(worker.poll(), 'the same renderer process must handle both files')
            finally:
                worker.stdin.close()
                worker.wait(timeout=5)
                worker.stdout.close()

    def test_worker_reports_file_error_and_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / 'valid.md'
            valid.write_text('A valid document', encoding='utf-8')
            worker = start_worker()
            try:
                self.assertIsNone(worker.poll(), 'renderer worker must remain alive for requests')
                error = render_request(worker, valid.with_name('missing.md'))
                self.assertFalse(error['ok'])
                self.assertIn('missing.md', error['error'])
                result = render_request(worker, valid)
                self.assertTrue(result['ok'], result)
            finally:
                worker.stdin.close()
                worker.wait(timeout=5)
                worker.stdout.close()


class TerminalNavigationTests(unittest.TestCase):
    def test_percentage_jump_uses_scrollable_progress_range(self):
        for percent, expected in ((0, 0), (22, 84), (50, 190), (100, 380)):
            with self.subTest(percent=percent):
                self.assertEqual(mdview.percentage_offset(percent, 500, 120), expected)
        self.assertEqual(mdview.percentage_offset(50, 40, 120), 0)
        for invalid in (-1, 101):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                mdview.percentage_offset(invalid, 500, 120)

    def test_arrow_keys_match_vim_actions(self):
        for mode in ('picker', 'preview'):
            for code, letter in ((mdview.curses.KEY_UP, 'k'), (mdview.curses.KEY_DOWN, 'j')):
                self.assertEqual(mdview.navigation_action(mode, mdview.key_text(code)),
                                 mdview.navigation_action(mode, letter, True))
        for key in ('RIGHT', 'l'):
            self.assertEqual(mdview.navigation_action('picker', key, key == 'l'), 'open')
            self.assertIsNone(mdview.navigation_action('preview', key, key == 'l'))
        for key in ('LEFT', 'h'):
            self.assertEqual(mdview.navigation_action('preview', key, key == 'h'), 'back')
            self.assertEqual(mdview.navigation_action('picker', key, key == 'h'), 'back')
        self.assertEqual(mdview.key_text(mdview.curses.KEY_RIGHT), 'RIGHT')
        self.assertEqual(mdview.key_text(mdview.curses.KEY_LEFT), 'LEFT')
        self.assertEqual(mdview.key_text(mdview.curses.KEY_ENTER), 'ENTER')
        self.assertEqual(mdview.key_text(ord('e')), 'e')
        self.assertEqual(mdview.key_text(mdview.curses.KEY_SR), '')

    def test_home_end_jump_to_edges(self):
        for mode in ('picker', 'preview'):
            self.assertEqual(mdview.navigation_action(mode, mdview.key_text(mdview.curses.KEY_HOME)), 'top')
            self.assertEqual(mdview.navigation_action(mode, mdview.key_text(mdview.curses.KEY_END)), 'bottom')

    def test_resize_keeps_picker_and_preview_drawing_inside_current_bounds(self):
        class Screen:
            def __init__(self):
                self.size = (24, 100)
                self.events = iter(((mdview.curses.KEY_RESIZE, (6, 20)),
                                    (mdview.curses.KEY_RIGHT, None), (mdview.curses.KEY_RESIZE, (2, 8)),
                                    (mdview.curses.KEY_LEFT, None), (mdview.curses.KEY_RESIZE, (24, 100)),
                                    (ord('q'), None)))

            def timeout(self, milliseconds): pass
            def erase(self): pass
            def clear(self): pass
            def refresh(self): pass
            def getmaxyx(self): return self.size
            def addnstr(self, row, column, text, limit, attr=0):
                rows, cols = self.size
                if not (0 <= row < rows and 0 <= column < cols and column + limit < cols):
                    raise AssertionError('drawing outside resized screen')
            def move(self, row, column):
                rows, cols = self.size
                if not (0 <= row < rows and 0 <= column < cols):
                    raise AssertionError('moving outside resized screen')
            def getch(self):
                key, size = next(self.events)
                if size:
                    self.size = size
                return key

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'note.md').write_text('# Note', encoding='utf-8')
            image = root / 'page.png'
            Image.new('RGBA', (1000, 500)).save(image)
            with patch('mdview.Path.cwd', return_value=root), \
                 patch('mdview.request_render', return_value={'ok': True, 'image': str(image)}), \
                 patch('mdview.clear_kitty_images'), patch('mdview.display_kitty_image'):
                mdview.picker(Screen(), object(), 24, 100, 1000, 480)

    def test_scroll_moves_one_row_and_stops_at_document_edges(self):
        self.assertEqual(mdview.scroll_offset(0, 'next', 200, 80, 20), 20)
        self.assertEqual(mdview.scroll_offset(0, 'previous', 200, 80, 20), 0)
        self.assertEqual(mdview.scroll_offset(110, 'next', 200, 80, 20), 120)
        self.assertEqual(mdview.scroll_offset(0, 'next', 40, 80, 20), 0)
        self.assertEqual(mdview.scroll_offset(60, 'top', 200, 80, 20), 0)
        self.assertEqual(mdview.scroll_offset(60, 'bottom', 200, 80, 20), 120)
        self.assertEqual(mdview.scroll_offset(0, 'bottom', 40, 80, 20), 0)

    def test_gg_requires_two_consecutive_g_keys_and_other_keys_cancel_prefix(self):
        self.assertEqual(mdview.navigation_input('picker', 'g', False, True), (None, True))
        self.assertEqual(mdview.navigation_input('picker', 'g', True, True), ('top', False))
        self.assertEqual(mdview.navigation_input('picker', 'j', True, True), ('down', False))
        self.assertEqual(mdview.navigation_input('preview', 'q', True), ('quit', False))
        self.assertEqual(mdview.navigation_input('preview', 'G', True, True), ('bottom', False))
        self.assertEqual(mdview.navigation_input('picker', 'DOWN', True), ('down', False))
        for mode in ('picker', 'preview'):
            self.assertEqual(mdview.navigation_input(mode, 'e', True), ('edit', False))

    def test_scrolling_viewport_preserves_pixels_across_strip_boundaries(self):
        image = Image.new('RGBA', (20, 200))
        for y in range(200):
            image.paste((y, 0, 0, 255), (0, y, 20, y + 1))
        viewport = mdview.crop_viewport(image, 60, 80)
        self.assertEqual(viewport.size, (20, 80))
        self.assertEqual(viewport.getpixel((0, 0)), (60, 0, 0, 255))
        self.assertEqual(viewport.getpixel((0, 79)), (139, 0, 0, 255))

    def test_kitty_clear_escape_sequence_reaches_terminal_stdout(self):
        output = io.StringIO()
        with patch('mdview.sys.stdout', output):
            mdview.clear_kitty_images()
        self.assertEqual(output.getvalue(), '\x1b_Ga=d,d=A,q=2\x1b\\')

    def test_kitty_image_chunks_preserve_png_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'image.png'
            data = bytes(range(256)) * 50
            path.write_bytes(data)
            output = io.StringIO()
            with patch('mdview.sys.stdout', output):
                mdview.display_kitty_image(path)
            commands = output.getvalue().split('\x1b_G')[1:]
            chunks = [command.split(';', 1)[1][:-2] for command in commands]
            self.assertGreater(len(chunks), 1)
            self.assertTrue(all(len(chunk) <= 4096 for chunk in chunks))
            self.assertEqual(base64.b64decode(''.join(chunks)), data)
            self.assertIn('m=0;', commands[-1])

    def test_vim_keys_map_to_picker_and_preview_actions(self):
        action = lambda mode, key: mdview.navigation_action(mode, key, True)
        self.assertEqual(action('picker', 'j'), 'down')
        self.assertEqual(action('picker', 'k'), 'up')
        for key in ('\n', '\r', 'ENTER'):
            self.assertIsNone(action('picker', key))
        self.assertEqual(action('picker', 'q'), 'quit')
        self.assertEqual(action('preview', 'j'), 'next')
        self.assertEqual(action('preview', 'k'), 'previous')
        self.assertEqual(action('preview', 'q'), 'quit')
        for mode in ('picker', 'preview'):
            self.assertEqual(action(mode, 'gg'), 'top')
            self.assertEqual(action(mode, 'G'), 'bottom')

    def test_picker_selection_stays_within_file_list(self):
        move = getattr(mdview, 'move_selection', lambda index, action, count: index)
        self.assertEqual(move(0, 'up', 3), 0)
        self.assertEqual(move(0, 'down', 3), 1)
        self.assertEqual(move(2, 'down', 3), 2)
        self.assertEqual(move(1, 'top', 3), 0)
        self.assertEqual(move(1, 'bottom', 3), 2)
        self.assertEqual(move(0, 'bottom', 0), 0)

    def test_picker_files_are_sorted_markdown_in_current_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'z.MD').touch()
            (root / 'a.markdown').touch()
            (root / 'b.txt').touch()
            (root / 'sub').mkdir()
            (root / 'sub' / 'nested.md').touch()
            (root / '.hidden').mkdir()
            (root / '.hidden' / 'ignored.md').touch()
            self.assertEqual([str(p.relative_to(root)) for p in mdview.markdown_files(root)],
                             ['a.markdown', 'z.MD'])

    def test_returning_from_preview_clears_image_before_picker_redraw(self):
        events = []

        class Screen:
            def clear(self):
                events.append('screen-clear')

            def refresh(self):
                events.append('screen-refresh')

        restore = getattr(mdview, 'restore_picker', lambda _screen: None)
        with patch('mdview.clear_kitty_images', side_effect=lambda: events.append('kitty-clear'), create=True):
            restore(Screen())
        self.assertEqual(events, ['kitty-clear', 'screen-clear', 'screen-refresh'])

    def test_picker_displays_rendered_png_for_selected_file(self):
        class Screen:
            def __init__(self):
                self.keys = iter((mdview.curses.KEY_RIGHT, mdview.curses.KEY_DOWN,
                                  mdview.curses.KEY_END, mdview.curses.KEY_HOME, mdview.curses.KEY_LEFT, ord('q')))

            def timeout(self, milliseconds): pass
            def erase(self): pass
            def clear(self): pass
            def addnstr(self, *args): pass
            def refresh(self): pass
            def move(self, *args): pass
            def getmaxyx(self): return (8, 80)
            def getch(self): return next(self.keys)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'note.md').write_text('# Note', encoding='utf-8')
            image = root / 'strip-00000.png'
            Image.new('RGBA', (640, 500)).save(image)
            with patch('mdview.Path.cwd', return_value=root), \
                 patch('mdview.request_render', return_value={'ok': True, 'image': str(image), 'strips': [str(image)]}), \
                 patch('mdview.clear_kitty_images'), \
                 patch('mdview.crop_viewport', wraps=mdview.crop_viewport) as crop, \
                 patch('mdview.display_kitty_image') as display:
                mdview.picker(Screen(), object(), 8, 80, 640, 160)
            self.assertEqual(display.call_args_list[0].args[0], root / 'viewport.png')
            self.assertEqual(display.call_count, 4, 'scrolling and jumps must redraw the viewport')
            self.assertEqual([call.args[1] for call in crop.call_args_list], [0, 20, 380, 0])

if __name__ == '__main__':
    unittest.main()
