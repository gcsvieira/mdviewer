import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()
