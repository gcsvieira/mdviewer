import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import mdview


class Screen:
    def __init__(self, keys=(), size=(8, 80)):
        self.keys = iter(keys)
        self.size = size
        self.events = []
        self.text = []

    def getmaxyx(self): return self.size
    def getch(self): return next(self.keys)
    def erase(self): pass
    def move(self, *args): pass
    def addnstr(self, row, column, text, *args): self.text.append(text)
    def keypad(self, enabled): self.events.append(('keypad', enabled))
    def clear(self): self.events.append('clear')
    def refresh(self): self.events.append('refresh')


class EditorTests(unittest.TestCase):
    def test_editor_command_preserves_flags_and_spaced_paths(self):
        path = Path('/tmp/notes with spaces/$(touch unwanted); note.md')
        cases = (({'EDITOR': 'nvim -f', 'VISUAL': 'nano'}, ['nvim', '-f']),
                 ({'EDITOR': '"/tmp/My Editor" --wait'}, ['/tmp/My Editor', '--wait']),
                 ({'EDITOR': '  ', 'VISUAL': 'nano -w'}, ['nano', '-w']),
                 ({'EDITOR': '', 'VISUAL': ''}, ['vi']))
        for environment, command in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                self.assertEqual(mdview.editor_command(path), [*command, str(path.resolve())])

    def test_editor_restores_terminal_after_success_nonzero_and_launch_failure(self):
        for outcome, expected in ((0, None), (130, '130'), (OSError('missing editor'), 'missing editor')):
            with self.subTest(outcome=outcome):
                screen = Screen()
                events = screen.events
                with ExitStack() as stack:
                    stack.enter_context(patch.dict(os.environ, {'EDITOR': 'nvim -f'}))
                    for name in ('def_prog_mode', 'endwin', 'reset_prog_mode'):
                        stack.enter_context(patch('mdview.curses.' + name, side_effect=lambda n=name: events.append(n)))
                    stack.enter_context(patch('mdview.curses.curs_set', side_effect=lambda n: events.append(('cursor', n))))
                    stack.enter_context(patch('mdview.clear_kitty_images', side_effect=lambda: events.append('images-clear')))
                    stack.enter_context(patch('mdview.terminal_size', return_value=(8, 80, 640, 160)))
                    stack.enter_context(patch('mdview.curses.resizeterm'))

                    def run(command, **kwargs):
                        events.append('editor')
                        self.assertEqual(command, ['nvim', '-f', '/tmp/note.md'])
                        self.assertEqual(kwargs, {}, 'editor must inherit the terminal without a shell')
                        if isinstance(outcome, Exception):
                            raise outcome
                        return subprocess.CompletedProcess(command, outcome)

                    stack.enter_context(patch('mdview.subprocess.run', side_effect=run))
                    error = mdview.edit_file(screen, Path('/tmp/note.md'))
                if expected:
                    self.assertIn(expected, error)
                else:
                    self.assertIsNone(error)
                self.assertEqual(events, ['images-clear', 'def_prog_mode', 'endwin', 'editor',
                                          'reset_prog_mode', ('keypad', True), ('cursor', 0), 'clear', 'refresh'])

    def test_malformed_editor_configuration_keeps_terminal_active(self):
        with patch.dict(os.environ, {'EDITOR': '"unterminated'}), \
             patch('mdview.curses.endwin') as leave, patch('mdview.subprocess.run') as run:
            error = mdview.edit_file(Screen(), Path('/tmp/note.md'))
        self.assertIn('editor', error.lower())
        leave.assert_not_called()
        run.assert_not_called()

    def test_resize_during_editor_restores_current_screen_bounds(self):
        screen = Screen()
        with patch.dict(os.environ, {'EDITOR': 'vi'}), ExitStack() as stack:
            for name in ('def_prog_mode', 'endwin', 'reset_prog_mode', 'curs_set'):
                stack.enter_context(patch('mdview.curses.' + name))
            stack.enter_context(patch('mdview.clear_kitty_images'))
            stack.enter_context(patch('mdview.subprocess.run', return_value=subprocess.CompletedProcess([], 0)))
            stack.enter_context(patch('mdview.terminal_size', return_value=(4, 20, 160, 80)))
            resize = stack.enter_context(patch('mdview.curses.resizeterm',
                                              side_effect=lambda r, c: setattr(screen, 'size', (r, c))))
            self.assertIsNone(mdview.edit_file(screen, Path('/tmp/note.md')))
            resize.assert_called_once_with(4, 20)
        self.assertEqual(screen.getmaxyx(), (4, 20))


class EditorPickerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.note = self.root / 'note.md'
        self.note.write_text('# Original', encoding='utf-8')
        self.page = self.root / 'page.png'
        Image.new('RGBA', (640, 500)).save(self.page)
        self.worker = object()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('mdview.Path.cwd', return_value=self.root))
        self.stack.enter_context(patch('mdview.clear_kitty_images'))
        self.stack.enter_context(patch('mdview.display_kitty_image'))

    def run_picker(self, screen):
        mdview.picker(screen, self.worker, 8, 80, 640, 160)

    def test_enter_does_not_open_selected_file(self):
        for key in (10, 13, mdview.curses.KEY_ENTER):
            with self.subTest(key=key), patch('mdview.request_render') as render:
                self.run_picker(Screen((key, ord('q'))))
                render.assert_not_called()

    def test_q_exits_directly_from_preview_and_clears_image(self):
        with patch('mdview.request_render', return_value={'ok': True, 'image': str(self.page)}), \
             patch('mdview.restore_picker') as restore, patch('mdview.clear_kitty_images') as clear:
            self.run_picker(Screen((ord('l'), ord('q'))))
        restore.assert_not_called()
        self.assertEqual(clear.call_count, 2, 'clear before displaying and when quitting')

    def test_edit_from_list_preserves_selected_path_after_rescan(self):
        self.note.rename(self.root / 'b.md')
        selected = self.root / 'c.md'
        selected.write_text('# Selected', encoding='utf-8')

        def edit(_screen, path):
            self.assertEqual(path, selected)
            (self.root / 'a.md').write_text('# New', encoding='utf-8')

        with patch('mdview.edit_file', side_effect=edit) as editor, \
             patch('mdview.request_render', return_value={'ok': True, 'image': str(self.page)}) as render:
            self.run_picker(Screen((ord('j'), ord('e'), ord('l'), ord('h'), ord('q'))))
        editor.assert_called_once()
        self.assertEqual(render.call_args.args[1]['path'], str(selected))

    def test_edit_preview_reuses_worker_preserves_offset_and_refreshes_saved_failure(self):
        updated = self.root / 'updated.png'
        Image.new('RGBA', (640, 200)).save(updated)

        def edit(_screen, path):
            path.write_text('# Edited and shorter', encoding='utf-8')
            return 'Editor exited with status 1'

        screen = Screen((ord('l'), ord('G'), ord('e'), ord('h'), ord('q')))
        with patch('mdview.edit_file', side_effect=edit), \
             patch('mdview.request_render', side_effect=[{'ok': True, 'image': str(self.page)},
                                                       {'ok': True, 'image': str(updated)}]) as render, \
             patch('mdview.crop_viewport', wraps=mdview.crop_viewport) as crop:
            self.run_picker(screen)
        self.assertEqual([call.args[0] for call in render.call_args_list], [self.worker, self.worker])
        self.assertEqual([call.args[1] for call in crop.call_args_list], [0, 380, 80])
        self.assertEqual(self.note.read_text(), '# Edited and shorter')
        self.assertTrue(any('Editor exited with status 1' in text for text in screen.text))

    def test_deleted_file_and_render_failure_return_to_list_with_error(self):
        for delete in (False, True):
            with self.subTest(delete=delete):
                self.note.write_text('# Original', encoding='utf-8')
                screen = Screen((ord('l'), ord('e'), ord('q')))

                def edit(_screen, path):
                    if delete:
                        path.unlink()

                with patch('mdview.edit_file', side_effect=edit), \
                     patch('mdview.request_render', side_effect=[{'ok': True, 'image': str(self.page)},
                                                               {'ok': False, 'error': 'render failed'}]) as render:
                    self.run_picker(screen)
                self.assertEqual(render.call_count, 1 if delete else 2)
                self.assertTrue(any(('no longer exists' if delete else 'render failed') in text
                                    for text in screen.text))

    def test_empty_list_ignores_edit(self):
        self.note.unlink()
        with patch('mdview.edit_file') as editor:
            self.run_picker(Screen((ord('e'), ord('q'))))
        editor.assert_not_called()
