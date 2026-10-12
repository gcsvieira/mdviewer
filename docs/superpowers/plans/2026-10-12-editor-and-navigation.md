# External Editor and Navigation Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan task-by-task in the current session. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add `e` to edit Markdown in the configured editor and arrow/Home/End alternatives to Vim navigation.

**Architecture:** Extend the existing curses input decoder and suspend curses around a synchronous editor subprocess. Keep the renderer alive and reload an edited preview after restoring the terminal.

**Tech Stack:** Existing Python, curses, subprocess, WebKitGTK, Kitty; stdlib `shlex` for editor arguments. No dependencies added.

**Spec:** [External editor and navigation design](../specs/2026-10-12-editor-and-navigation-design.md).

## Global constraints

- `e` works in both the file list and the preview.
- Read nonempty `$EDITOR` first; fall back to nonempty `$VISUAL`, then `vi`.
- The editor inherits stdin, stdout, and stderr and runs synchronously in the same terminal.
- Always restore curses and hide the cursor when the editor finishes or fails to start.
- Keep the WebKit worker alive.
- No built-in editor, save command, file watcher, editor selection menu, or new dependency.
- Quick inline output remains unchanged. The Markdown layout keeps its original render width after resizing.

## Review focus

1. A pending `g` followed by an arrow or `e` must not swallow that action — Task 1.
2. Editor flags, quoted paths, and filenames with spaces must remain separate arguments without shell interpretation — Task 2.
3. Failed launch, invalid configuration, and nonzero editor exit must restore the terminal and leave navigation usable — Task 2.
4. Resizing inside the editor must not recreate the curses drawing crash on return — Task 2.
5. Shortening, renaming, or deleting the edited file must not leave a stale preview or out-of-range selection — Task 2.

## Task 1: Add keyboard alternatives

**Files:** Modify `mdview.py`, `tests/test_mdview.py`, `README.md`.

**Interfaces:**
- Consumes `navigation_action(mode, key)`, `navigation_input(mode, key, pending_g)`, `move_selection`, and `scroll_offset`.
- Produces `key_text(key: int) -> str`, mapping curses key codes to `UP`, `DOWN`, `LEFT`, `RIGHT`, `HOME`, `END`, and `ENTER`; ordinary character codes retain their characters. Unsupported codes return an empty string.
- `navigation_action` also maps `e` to `edit` in both modes; Task 2 implements that action.

- [x] Add tests to `TerminalNavigationTests`: `test_arrow_keys_match_vim_actions` asserts Up/Down match `k/j` in both modes; Right and `l` open only in the list; Left and `h` return only in the preview.
- [x] Add `test_home_end_jump_to_edges`: assert Home maps to `top` and End to `bottom`, in both modes. Test `key_text` using the actual curses constants.
- [x] Extend `test_gg_requires_two_consecutive_g_keys_and_other_keys_cancel_prefix`: assert `(mode='picker', key='DOWN', pending_g=True)` returns `('down', False)` and `e` returns `('edit', False)`. Assert `e` maps to `edit` in both modes.
- [x] Run `python3 -m unittest tests.test_mdview.TerminalNavigationTests`; confirm the new assertions fail.
- [x] Implement `key_text` and replace the two inline key conversions in `picker`. Add the key aliases from the spec to `navigation_action`; preserve the existing `gg` decoder.
- [x] Update the menu and preview footers and README with the working navigation aliases. Mention Home/End and `h`/`l`, without adding unimplemented features.
- [x] Run the focused tests. In Kitty, verify Up/Down, Home/End, Right/`l`, and Left/`h` in their applicable modes.
- [x] Commit: `feat: add arrow and home-end navigation`.

## Task 2: Hand off to the editor and refresh on return

**Files:** Modify `mdview.py`, `README.md`; create `tests/test_editor.py`.

**Interfaces:**
- Consumes Task 1's `edit` action, `request_render(worker, request)`, and existing image cleanup/drawing helpers.
- Produces `editor_command(path: Path) -> list[str]`, using the spec's environment precedence and `shlex.split`.
- Produces `edit_file(screen, path: Path) -> str | None`, which manages the terminal handoff, restores it in `finally`, and returns an error message or `None`.
- `picker` handles `edit` without replacing the worker; it rescans the list or reloads the preview according to the originating mode.

- [x] Add `EditorTests.test_editor_command_preserves_flags_and_spaced_paths`: with `$EDITOR='nvim -f'`, assert argv is `['nvim', '-f', str(path.resolve())]`. Cover quoted executable paths, literal shell metacharacters in filenames, empty variables, `$VISUAL` fallback, and final `vi` fallback.
- [x] Add `test_editor_restores_terminal_after_failure`: record the calls for clearing images, `def_prog_mode`, `endwin`, editor launch, `reset_prog_mode`, restoring keypad/cursor, and screen clearing. Assert the restoration happens after success, nonzero exit, `OSError`, and malformed quoting. Assert `subprocess.run` uses argument-list execution without a shell or redirected terminal streams.
- [x] Add `test_resize_during_editor_restores_current_screen_bounds`: simulate changed tty rows/columns; assert curses is resized to those dimensions before drawing resumes. Retain the existing resize regression tests.
- [x] Add picker-loop integration tests: editing from the list preserves the selected path and refreshes modification times; editing from preview rereads the file with the same worker and clamps its old offset after shortening. Deleting the file or failing to rerender returns to the list with an error. Editing an empty list launches nothing.
- [x] Run the focused tests; confirm the new assertions fail.
- [x] Implement `editor_command` and `edit_file`. After the editor exits, restore curses, obtain the current terminal dimensions, and call `curses.resizeterm` when needed. Return concise UI errors for launch/configuration failures and nonzero exit status.
- [x] Handle `edit` in `picker`. Reset the pending `g`, refresh the file list, and preserve selection by path where possible. Reload a preview even when the editor reports a nonzero status, because edits may have been saved. Reuse the existing render/load logic through one small helper if needed; keep its dimensions and error handling consistent with normal opening.
- [x] Update both footers and README to document `e`, editor precedence, command arguments, and return behavior. Document the wait-flag requirement for GUI editors briefly.
- [x] Run `python3 -m unittest discover -s tests`, `python3 -m py_compile mdview.py`, and `git diff --check`.
- [x] Run a Kitty smoke check with `$EDITOR` pointing to a small terminal-attached test editor: assert stdin/stdout are TTYs, rewrite a fixture, resize the window, exit, verify the refreshed preview and the original worker process, then return to the list and quit. Manually exercise the same handoff with a real terminal editor.
- [x] Commit: `feat: edit markdown in the configured editor`.

## Completion

Both keyboard styles work. Editing occupies the existing terminal, restores the original viewer mode, refreshes saved content, preserves selection/scroll position where possible, and leaves no stale image. The persistent renderer survives the editor session; quick output and the resize fix remain working.

Verified: 31 tests pass; Kitty smoke exercised arrows, Home/End, h/l, a terminal-attached editor, resizing during editing, refresh using the same worker, and a real Neovim save. Fresh review found a Ctrl+C propagation bug; the renderer now runs in its own session, with a real process-group interrupt regression test.
