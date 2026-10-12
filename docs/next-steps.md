# Next steps: navigation, folders, and settings

Status: all recorded next steps are implemented, including folder refresh, settings, exclusive keyboard modes, pagination, color selection, and loading feedback.

Configuration is saved at `~/.config/mdviewer/settings.json`, as explicitly requested by the user. Defaults: Vim mode off, scroll viewing, white foreground.

## Separate keyboard modes

Show and enable one navigation scheme at a time. Remove the combined arrow/Vim shortcut hints that clutter the current footers.

| Action | Vim mode off | Vim mode on |
| --- | --- | --- |
| Previous item / scroll up | Up | `k` |
| Next item / scroll down | Down | `j` |
| Open file or enter folder | Right | `l` |
| Return to file list / parent folder | Left | `h` |
| First item / document top | Home | `gg` |
| Last item / document bottom | End | `G` |

- Vim mode replaces arrow keys and Home/End with `hjkl` and `gg`/`G`; the two schemes are not active together.
- Enter no longer opens files. In the normal navigation mode, Right is the way to open a file.
- `q` exits the entire program from any screen, returning to the user's terminal. It no longer returns from a preview to the file list.
- Left, or `h` in Vim mode, returns from a preview to its containing folder's file list.
- Keep `e` for the existing external-editor workflow unless the user changes that requirement.
- Shortcut hints must reflect the selected mode and current screen.

### Jump to a percentage of the document

- In a file preview, accept a number from `0` to `100` and jump to that percentage of the existing progress scale.
- Vim mode: number followed by `G`, such as `22G`, `50G`, or `100G`.
- Non-Vim mode: number followed by Enter, such as `22` + Enter or `50` + Enter. This does not restore Enter as a shortcut for opening files in the picker.
- `0G` is equivalent to `gg`; `0` + Enter is equivalent to Home. `100G` or `100` + Enter jumps to the document bottom.
- Use the same scale as the preview's displayed percentage: `0%` is the top and `100%` is the furthest bottom position. Keep the jump location and percentage indicator consistent.
- Keep unprefixed `G` as the bottom shortcut in Vim mode. Percentage jumps apply to document previews, not file-list selection.
- Scroll jumps round to the nearest pixel in the existing scrollable range. Inputs are integers from 0–100; invalid values show an error without moving the viewport. Backspace edits the number, Escape cancels it, and another navigation key cancels the number while still performing its action. Paginated jumps snap to the nearest page, with the final page at 100%.

## Browse folders explicitly

- List folders and Markdown files in the current folder only.
- Do not flatten or recursively display nested Markdown files.
- Enter a folder using Right, or `l` in Vim mode, to see its contents.
- Use Left, or `h` in Vim mode, to return to the parent folder.
- Show the current folder so the user knows where they are.
- Returning from a file preview restores the containing folder and selected file.
- Automatically refresh the current folder's file list when new files appear, preserving the selected item where possible. No restart or manual refresh should be needed.

## Settings

Press `s` in the file picker to open a settings page.

| Setting | Values | Behavior |
| --- | --- | --- |
| `vim-mode` | on / off | Choose the exclusive navigation scheme above. |
| `file-navigation-style` | scroll / paginated | Choose how a rendered document is navigated. |
| `element-color` | white / black | Choose the rendered foreground/text palette for different terminal backgrounds. Preserve the transparent background. |

Navigation style is separate from keyboard mode: either keyboard scheme should work with either scroll or paginated viewing.

## File-opening progress

Show a loading bar or progress indicator somewhere while opening/rendering a file. The UI should visibly indicate that work is in progress.

Do not show a fabricated percentage if the renderer cannot report measurable progress. Decide the placement and progress reporting during implementation. The user has not specified a separate on/off setting for the indicator.

## Implemented decisions

- Defaults: Vim mode off, scroll navigation, white elements.
- Settings are applied immediately and saved to `~/.config/mdviewer/settings.json`. Right/`l` or Space changes a value; Left/`h`, Escape, or `s` returns to the picker.
- Pagination prefers paragraph/heading boundaries; oversized blocks split at terminal-row boundaries. Navigation moves one page at a time.
- Parent navigation stops at the initial folder. Explicit symlinks are followed normally. Folders sort before Markdown files; hidden entries and `node_modules` are excluded.
- The current folder is rescanned while idle on a 500 ms input timeout; selection is preserved by path.
- White/black applies to the picker/settings foreground and Markdown text, preserving the terminal background and meaningful accent colors.
- File opening uses an animated indeterminate bar, because the renderer does not expose measurable progress. `q` cancels rendering and exits cleanly.

## Keep existing behavior

Retain the background-only persistent renderer, external-editor handoff, resize safety, and quick inline command `mdview file.md`. Implementing these next steps must not introduce renderer windows.

Editing/navigation baseline: `58f129d` on `feat/persistent-terminal-viewer`. All remaining requirements are implemented and 50 tests pass. A real Kitty check covers folder refresh, preference persistence, both keyboard modes, pagination, palette changes, editing, and quitting during loading. This file records new requirements and supersedes conflicting keyboard and recursive-picker decisions in the earlier design documents.
