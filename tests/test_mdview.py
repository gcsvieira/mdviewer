import tempfile
import unittest
from pathlib import Path
from PIL import Image
import mdview


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


if __name__ == '__main__':
    unittest.main()
