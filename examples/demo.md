# Markdown in your terminal

An **Obsidian-inspired** preview with a transparent background, *proportional typography*, and `inline code`.

## Callouts

> [!NOTE] A small native renderer
> Markdown becomes HTML and CSS, then a transparent PNG through the system WebKit engine.

> [!TIP]+ Same terminal, no extra window
> Run `./mdview examples/demo.md` and keep working at your prompt.

> [!WARNING] Images contain pixels
> Terminal text selection and search do not work inside the rendered document.

## Tables and code

| Feature | First prototype |
|---|---|
| Background | Transparent |
| Alignment | Left |
| Long documents | Equal-width strips |

```python
from pathlib import Path
text = Path('notes.md').read_text()
print(text)
```

## A regular quote

> Keep the first version small enough to try.

- Headings, lists, and emphasis
- Relative images and links
- Expanded callouts

---

[Project repository](https://github.com/gcsvieira/mdviewer)
