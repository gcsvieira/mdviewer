# External Editor and Accessible Navigation

## Goal

Let users edit the selected Markdown file in their configured editor and navigate the viewer without knowing Vim keys. Keep the existing terminal workflow, persistent background renderer, and quick-print command.

## Keyboard behavior

| Action | Existing keys | Additional keys |
| --- | --- | --- |
| Select previous file / scroll up | `k` | Up |
| Select next file / scroll down | `j` | Down |
| First file / document top | `gg` | Home |
| Last file / document bottom | `G` | End |
| Open selected file | Enter, `l` | Right |
| Return from preview to file list | `q`, `h` | Left |
| Exit from file list | `q` | — |
| Edit selected or previewed file | — | `e` |

Home/End are the non-Vim alternatives to `gg`/`G`. Shifted arrow shortcuts are excluded. No custom escape-sequence parser is needed. Left does nothing in the file list; Right does nothing in the preview. A non-`g` key cancels a pending `gg` prefix and still performs its own action. An empty list ignores `e`.

## Editor handoff

- `e` works in both the file list and the preview.
- Read nonempty `$EDITOR` first; fall back to nonempty `$VISUAL`, then `vi`. This fallback order is approved.
- Split the configured command using `shlex.split`, append the absolute file path as a separate argument, and launch without a shell. Quoted executable paths, flags, and filenames containing spaces must work.
- Clear Kitty images, save curses' program state, and leave curses mode before launching. The editor inherits stdin, stdout, and stderr and runs synchronously in the same terminal.
- Always restore curses and hide the cursor when the editor finishes or fails to start. Reconcile the screen dimensions if the terminal resized while editing. Keep the WebKit worker alive.
- An editor that launches a separate GUI must be configured with its own wait flag; the viewer waits for the configured command to exit.

## Return behavior

- Editing from the list returns to the list, rescans Markdown files and modification times, and preserves the selected path where possible. If the file disappeared, clamp the previous selection to the remaining list.
- Editing from the preview rerenders the same file using the existing worker and preserves the previous vertical offset, clamped to the updated document height.
- If the file disappeared or rerendering fails, clear the old preview and return to the list with an error message.
- Launch failures, malformed editor configuration, and nonzero exit codes appear in the UI. Saved edits still refresh even when the editor exits unsuccessfully.
- Returning from the editor resets a pending `gg` prefix.

## Scope and verification

No built-in editor, save command, file watcher, editor selection menu, or new dependency. Quick inline output remains unchanged. The Markdown layout keeps its original render width after resizing.

Verify key aliases and prefix cancellation; argument handling; terminal restoration on every exit path; resizing while editing; saved edits, shortened/deleted files, and selection preservation. Exercise the handoff in Kitty with a terminal-attached test editor, then manually with a real terminal editor.
