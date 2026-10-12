# Repository Setup Implementation Plan

**Goal:** Initialize mdviewer locally and publish its initial files to GitHub using gh.

**Architecture:** Repository scaffolding only. The future application will open Markdown from a CLI in a lightweight native window; implementation choices remain open.

**Tech Stack:** Git and GitHub CLI for this phase.

**Spec:** The user's lightweight Markdown viewer/editor summary and repository setup request.

## Assumptions and constraints

- Proposed repository: `gcsvieira/mdviewer`, private initially.
- Default branch: `main`.
- No Electron or wikilink support required.
- Defer language, editor support, Markdown flavor, dependencies, and license selection.
- Preserve existing workspace files.

## Task 1: Prepare initial files

- [ ] Create `README.md` describing the goal, current planning status, and proposed CLI/viewer/live-reload workflow. Do not claim the app works yet.
- [ ] Create `.gitignore` excluding `.agents/`, `.aws/`, `.codex/`, common temporary files, and OS metadata. Add language-specific ignores when the language is chosen.
- [ ] Keep this plan under `docs/superpowers/plans/`.
- [ ] Review all initial files for scope and accidental secrets before staging.

## Task 2: Initialize local Git

- [x] Verify Git metadata write access; the previous read-only mount is gone.
- [ ] Run `git init -b main`.
- [ ] Verify author configuration with `git var GIT_AUTHOR_IDENT`.
- [ ] Stage only `README.md`, `.gitignore`, and this plan; inspect `git diff --cached`.
- [ ] Commit with `chore: initialize mdviewer repository`.
- [ ] Verify `git status --short` is clean and the initial commit contains only intended files.

## Task 3: Create and push the GitHub repository

- [ ] Verify network access and authentication with `gh api user --jq .login`.
- [ ] Confirm the proposed name and visibility before publishing; check whether that repository already exists.
- [ ] Run `gh repo create gcsvieira/mdviewer --private --source=. --remote=origin --push` if the repository does not exist.
- [ ] Verify `origin`, branch tracking, and remote repository visibility with `git remote -v`, `git status -sb`, and `gh repo view --json nameWithOwner,url,visibility,defaultBranchRef`.

## Verification and handoff

No application tests are needed for documentation and Git scaffolding. Success means the intended files are committed on `main`, pushed to the expected private GitHub repository, and the local working tree is clean. Next, choose Python versus Rust, viewer versus editor, and the Markdown extensions before implementation.

## Execution record

GitHub authentication verified as `gcsvieira` on 2026-10-12. The filesystem restriction was lifted, and Git initialized successfully on `main`. The user approved proceeding with the proposed private repository.

The remaining checklist items are verified during execution; the initial commit precedes remote creation and publication.
