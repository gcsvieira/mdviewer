import io
import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import ExitStack
from PIL import Image
from tests.test_editor import Screen

import mdview


class BrowserTests(unittest.TestCase):
    def test_settings_persist_in_home_config_mdviewer(self):
        with tempfile.TemporaryDirectory() as directory, patch('mdview_settings.Path.home', return_value=Path(directory)):
            settings = mdview.Settings(vim_mode=True, file_navigation_style='paginated', element_color='black')
            mdview.save_settings(settings)
            path = Path(directory) / '.config/mdviewer/settings.json'
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text())['vim-mode'], True)
            self.assertEqual(mdview.load_settings(), settings)

    def test_invalid_preferences_fall_back_to_valid_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{broken')
            self.assertEqual(mdview.load_settings(path), mdview.Settings())
            path.write_text(json.dumps({'vim-mode': 'yes', 'file-navigation-style': 'other',
                                        'element-color': 'black'}))
            self.assertEqual(mdview.load_settings(path), mdview.Settings(element_color='black'))

    def test_keyboard_modes_are_exclusive(self):
        for mode in ('picker', 'preview', 'settings'):
            for key in ('j', 'k', 'h', 'l', 'gg', 'G'):
                self.assertIsNone(mdview.navigation_action(mode, key, False))
            for key in ('UP', 'DOWN', 'LEFT', 'RIGHT', 'HOME', 'END'):
                self.assertIsNone(mdview.navigation_action(mode, key, True))
            self.assertEqual(mdview.navigation_action(mode, 'q', False), 'quit')
            self.assertEqual(mdview.navigation_action(mode, 'q', True), 'quit')
        self.assertEqual(mdview.navigation_action('picker', 'RIGHT', False), 'open')
        self.assertEqual(mdview.navigation_action('picker', 'l', True), 'open')
        self.assertEqual(mdview.navigation_action('preview', 'LEFT', False), 'back')
        self.assertEqual(mdview.navigation_action('preview', 'h', True), 'back')
        self.assertEqual(mdview.navigation_action('picker', 's', False), 'settings')

    def test_folder_entries_are_shallow_and_folders_sort_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notes').mkdir()
            (root / 'notes/nested.md').write_text('# Nested')
            (root / 'z.md').write_text('# Z')
            (root / 'ignored.txt').touch()
            (root / '.hidden').mkdir()
            self.assertEqual([path.name for path in mdview.directory_entries(root)], ['notes', 'z.md'])
            self.assertEqual([path.name for path in mdview.directory_entries(root / 'notes')], ['nested.md'])

    def test_pages_break_at_blocks_and_cover_oversized_blocks(self):
        self.assertEqual(mdview.page_offsets(500, 200, 20, [0, 150, 300]), [0, 150, 300])
        self.assertEqual(mdview.page_offsets(500, 200, 20, []), [0, 200, 400])
        self.assertEqual(mdview.page_offsets(100, 200, 20, []), [0])
        pages = [0, 150, 300]
        self.assertEqual(mdview.page_for_percentage(0, pages), 0)
        self.assertEqual(mdview.page_for_percentage(50, pages), 1)
        self.assertEqual(mdview.page_for_percentage(100, pages), 2)

    def test_black_palette_overrides_text_without_an_opaque_background(self):
        html = mdview.render_html('# Heading\n\nText', Path('/tmp'), 'black')
        self.assertIn('color: #171717', html)
        self.assertIn('background: transparent', html)

    def test_loading_progress_callbacks_run_until_result_arrives(self):
        worker = SimpleNamespace(stdin=io.StringIO(), responses=queue.Queue(), poll=lambda: None)
        timer = threading.Timer(.25, lambda: worker.responses.put('{"ok":true}\n'))
        calls = []
        timer.start()
        try:
            self.assertEqual(mdview.request_render(worker, {}, timeout=1,
                                                   progress=lambda: calls.append('frame')), {'ok': True})
        finally:
            timer.join()
        self.assertGreaterEqual(len(calls), 1)


class BrowserIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.page = self.root / 'page.png'
        Image.new('RGBA', (640, 500)).save(self.page)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('mdview.Path.cwd', return_value=self.root))
        self.stack.enter_context(patch('mdview.clear_kitty_images'))
        self.stack.enter_context(patch('mdview.display_kitty_image'))
        self.stack.enter_context(patch('mdview.save_settings'))
        self.stack.enter_context(patch('mdview.apply_palette'))
        self.render = self.stack.enter_context(patch('mdview.request_render', return_value={
            'ok': True, 'image': str(self.page), 'boundaries': [0, 100, 220, 330, 440]}))

    def browse(self, screen, settings=None):
        mdview.picker(screen, object(), 8, 80, 640, 160, settings=settings or mdview.Settings())

    def test_folder_browsing_returns_to_containing_folder_then_parent(self):
        folder = self.root / 'notes'
        folder.mkdir()
        (folder / 'nested.md').write_text('# Nested')
        (self.root / 'root.md').write_text('# Root')
        screen = Screen((mdview.curses.KEY_RIGHT, mdview.curses.KEY_RIGHT,
                         mdview.curses.KEY_LEFT, mdview.curses.KEY_LEFT,
                         mdview.curses.KEY_DOWN, mdview.curses.KEY_RIGHT, ord('q')))
        self.browse(screen)
        self.assertEqual([call.args[1]['path'] for call in self.render.call_args_list],
                         [str(folder / 'nested.md'), str(self.root / 'root.md')])
        self.assertIn('notes/', screen.text)

    def test_new_files_appear_while_picker_is_idle(self):
        (self.root / 'a.md').write_text('# A')
        screen = Screen((mdview.curses.KEY_END, mdview.curses.KEY_RIGHT, ord('q')))
        original = screen.getch
        first = True

        def getch():
            nonlocal first
            if first:
                first = False
                (self.root / 'new.md').write_text('# New')
                return -1
            return original()

        screen.getch = getch
        self.browse(screen)
        self.assertEqual(self.render.call_args.args[1]['path'], str(self.root / 'new.md'))

    def test_refresh_preserves_selection_when_a_file_is_inserted_before_it(self):
        (self.root / 'z.md').write_text('# Selected')
        screen = Screen((mdview.curses.KEY_RIGHT, ord('q')))
        original = screen.getch
        first = True

        def getch():
            nonlocal first
            if first:
                first = False
                (self.root / 'a.md').write_text('# Added')
                return -1
            return original()

        screen.getch = getch
        self.browse(screen)
        self.assertEqual(self.render.call_args.args[1]['path'], str(self.root / 'z.md'))

    def test_failed_settings_save_keeps_viewer_usable(self):
        (self.root / 'note.md').write_text('# Note')
        screen = Screen((ord('s'), mdview.curses.KEY_RIGHT, 27, ord('l'), ord('q')))
        with patch('mdview.save_settings', side_effect=OSError('read-only')):
            self.browse(screen)
        self.assertTrue(any('Could not save settings' in text for text in screen.text))
        self.assertEqual(self.render.call_count, 1)

    def test_settings_change_keys_style_and_color_and_return_to_picker(self):
        (self.root / 'note.md').write_text('# Note')
        settings = mdview.Settings()
        screen = Screen((ord('s'), mdview.curses.KEY_RIGHT, mdview.curses.KEY_DOWN,
                         ord('j'), ord('l'), ord('j'), ord('l'), ord('h'), ord('l'), ord('q')))
        self.browse(screen, settings)
        self.assertEqual(settings, mdview.Settings(True, 'paginated', 'black'))
        self.assertEqual(self.render.call_args.args[1]['element_color'], 'black')

    def test_paginated_preview_moves_by_blocks_and_percentage_jumps_to_a_page(self):
        (self.root / 'note.md').write_text('# Note')
        screen = Screen((mdview.curses.KEY_RIGHT, mdview.curses.KEY_DOWN, mdview.curses.KEY_END,
                         mdview.curses.KEY_HOME, ord('5'), ord('0'), 13, ord('q')))
        with patch('mdview.crop_viewport', wraps=mdview.crop_viewport) as crop:
            self.browse(screen, mdview.Settings(file_navigation_style='paginated'))
        self.assertEqual([call.args[1] for call in crop.call_args_list], [0, 100, 440, 0, 220])
        self.assertEqual(crop.call_args_list[0].args[2], 100)

    def test_percentage_terminator_matches_keyboard_mode(self):
        (self.root / 'note.md').write_text('# Note')
        for vim in (False, True):
            opening = ord('l') if vim else mdview.curses.KEY_RIGHT
            wrong, correct = (13, ord('G')) if vim else (ord('G'), 13)
            screen = Screen((opening, ord('2'), ord('2'), wrong, ord('5'), ord('0'), correct, ord('q')))
            with self.subTest(vim=vim), patch('mdview.crop_viewport', wraps=mdview.crop_viewport) as crop:
                self.browse(screen, mdview.Settings(vim_mode=vim))
                self.assertEqual(crop.call_args.args[1], 190)
                self.assertNotIn(84, [call.args[1] for call in crop.call_args_list])
