# dff — Test plan

Living checklist. Each `[ ]` is a test case we intend to write; flip it to
`[x]` when the test exists, is passing, and the corresponding feature is
actually shipped. See `CLAUDE.md` for the TDD workflow.

Stack: `pytest`, `pytest-asyncio`, `pytest-textual-snapshot`, optional
`pytest-benchmark`. Fixture repos are built by shelling out to real `git`
and `jj` in `tmp_path`.

Run locally:

```bash
uv run pytest                       # all tests
uv run pytest -k tree               # filter
uv run pytest --snapshot-update     # regenerate SVG snapshots after
                                    # intentional UI changes
uv run pytest -m smoke              # CI-only tmux smoke layer
```

---

## 1. VCS backends

### 1.1 Detect (`vcs/detect.py`)

- [ ] Picks `jj` when only `.jj/` is present.
- [ ] Picks `git` when only `.git/` is present.
- [ ] Picks `jj` when both are present (default `vcs.prefer = auto`).
- [ ] `--backend git` overrides auto-detect.
- [ ] Raises a clear error when neither is present.
- [ ] Walks up parent dirs to find the repo root.

### 1.2 git backend (`vcs/git.py`)

- [ ] `list_changes()` returns a `Staged` and an `Unstaged` group.
- [ ] `Staged` is empty when nothing is staged; group is omitted from tree.
- [ ] `Unstaged` lists modified tracked files.
- [ ] File status parses to `M` / `A` / `D` / `R` correctly (incl. renames
      with similarity score).
- [ ] `+N -N` stats match `git diff --numstat`.
- [ ] `get_sides(path)` returns `(HEAD_content, index_content)` for staged
      and `(index_content, worktree_content)` for unstaged.
- [ ] Binary files flagged and skipped from diff rendering.
- [ ] Detached HEAD / empty repo / initial commit edge cases don't crash.
- [ ] Conflict detection via `git ls-files -u` returns the unmerged set.
- [ ] `get_conflict_sides(path)` returns `{base, ours, theirs}` from
      `git show :1:/:2:/:3:`; missing base tolerated.

### 1.3 jj backend (`vcs/jj.py`)

- [ ] `list_changes()` uses the configured revset (default `trunk()..@`).
- [ ] Revset fallback to `@-::@` when `trunk()` is unconfigured.
- [ ] `--rev` CLI flag overrides config.
- [ ] All commands pass `--ignore-working-copy`.
- [ ] Each change exposes `change_id`, `short_id`, `description`,
      `author`, `timestamp`.
- [ ] `list_files(change_id)` parses `--summary` into `M/A/D/R` + stats.
- [ ] `get_sides(change_id, path)` uses `jj file show -r <id>-` and
      `-r <id>` for before/after.
- [ ] Root `change_id` = `zzzzzzzz` is handled (no parent).
- [ ] Empty description rendered as `(no description set)`.
- [ ] Conflict detection via `jj resolve --list`.
- [ ] `get_conflict_sides` resolves each parent via
      `parents.map(|p| p.change_id())` and fetches snapshots.
- [ ] `jj` binary missing → actionable error message.

### 1.4 Backend abstract surface (`vcs/base.py`)

- [ ] `Backend` protocol is satisfied by both `GitBackend` and `JjBackend`
      (checked via `@runtime_checkable` + isinstance).
- [ ] `FileChange` instances are hashable (used as dict keys in UI).
- [ ] `Change.stats()` aggregates file-level `+N -N` correctly.

---

## 2. Models

### 2.1 `models/change.py`

- [ ] `HunkStats.__add__` for group aggregation.
- [ ] `FileChange.is_binary` / `is_conflict` / `is_rename` helpers.

### 2.2 `models/comment.py`

- [ ] `Comment` stores `file`, `side` (`LEFT | RIGHT | HUNK | OURS |
      THEIRS | BASE`), `line_range`, `body`, `content_hash`.
- [ ] `CommentStore.add` / `remove` / `edit` behave as expected.
- [ ] Re-anchor: when hunk map shifts by +3 lines and content matches,
      stored line range is shifted by +3.
- [ ] Re-anchor: when content hash no longer matches, comment is marked
      `stale` but retained.
- [ ] Re-anchor: when the file is deleted, all its comments go stale.
- [ ] Re-anchor preserves ordering and IDs.
- [ ] `cross_side` rejection / split / ask behavior honored from config.

---

## 3. Prompt export (`prompt.py`)

- [ ] Default template groups by file.
- [ ] Each comment renders its side label (`LEFT, removed` /
      `RIGHT, added` / `hunk-level` / `OURS` / `THEIRS` / `BASE`).
- [ ] Fenced `diff` code block embedded when
      `comment.include_code_snippet = true`.
- [ ] `stale` comments render with a `(stale)` marker.
- [ ] Custom Jinja template path loads and overrides default.
- [ ] Clipboard write goes through `pyperclip`; when clipboard disabled,
      content is written to `comment.export_path`.

---

## 4. Widgets (Pilot-driven)

### 4.1 Change tree (`widgets/change_tree.py`)

- [ ] Renders one group per change (jj) or `Staged` / `Unstaged` (git).
- [ ] Displays `M/A/D/R` badges with correct colors.
- [ ] Displays `+N -N` per file and aggregate per group.
- [ ] `j` / `k` navigate items, wrapping at ends or stopping (per config).
- [ ] `J` / `K` jump to next/prev change group.
- [ ] `Enter` / `Space` on a directory folds/unfolds it.
- [ ] Single-child directories auto-collapse when configured.
- [ ] Ignored files (glob) render dimmed.
- [ ] Conflict files render with `!` badge in red.

### 4.2 Diff panel (`widgets/diff_panel.py`)

- [ ] Mounts `CollapsibleDiffView` with correct `before` / `after`.
- [ ] Header pill shows `<path>  <status>  +N -N` and mode pill.
- [ ] `m` toggles `split` ↔ `unified`.
- [ ] `w` toggles word wrap; preserves scroll position.
- [ ] Language auto-detected from filename for syntax highlighting.
- [ ] Large file (> `performance.max_file_lines`) falls back to plain
      text with a notice pill.

### 4.3 Collapsible diff (`widgets/collapsible_diff.py`)

- [ ] Unchanged regions longer than `fold.context_lines * 2 +
      always_expand_small` are folded.
- [ ] Each fold renders an `N hidden lines ▾` marker.
- [ ] Clicking the marker expands that fold only.
- [ ] `Enter` on the fold marker (keyboard) also expands.
- [ ] Expanded state survives a watcher refresh when the hunk map still
      contains the same region.
- [ ] Split mode folds stay synchronized across both columns.

### 4.4 Line selection (`widgets/line_selection.py`)

- [ ] `Space` toggles the current line in the selection set.
- [ ] `Shift+↑` / `Shift+↓` extends selection.
- [ ] Mouse click-drag across lines produces a contiguous selection.
- [ ] Selection is confined to a single side by default.
- [ ] Cross-side drag triggers `cross_side` behavior (ask / split /
      reject) per config.
- [ ] `h` / `l` switch focused column in split mode; current side
      reflects focus.
- [ ] `[` / `]` force side on context lines in unified mode.
- [ ] `Esc` clears the selection.

### 4.5 Comment bar (`widgets/comment_bar.py`)

- [ ] `c` focuses input, prefills anchor string
      (`<path> <range> (<SIDE>, <verb>)`).
- [ ] `Enter` submits a comment and clears input.
- [ ] `Shift+Enter` / `Ctrl+J` inserts newline in the input.
- [ ] `Esc` cancels without committing.
- [ ] List above input shows `▸ <path> <range> <preview>`.
- [ ] `g c` focuses the list.
- [ ] `Enter` on a list item jumps to the anchor (file, folds, scroll).
- [ ] `e` edits an existing comment; `d` deletes with confirm.
- [ ] `y` (or `[ copy ]` click) writes markdown prompt to clipboard.
- [ ] Stale comments are dimmed and annotated; still copyable.

### 4.6 Status bar (`widgets/status_bar.py`)

- [ ] Renders hints separated by `·`.
- [ ] Hints change based on focused widget (context-aware).
- [ ] `?` opens help overlay; `Esc` closes it.

---

## 5. Integration

### 5.1 Responsive layout (`layout.py`)

- [ ] Width ≥ 140 → tree + split diff + comment bar simultaneously.
- [ ] 100 ≤ width < 140 → tree + unified diff.
- [ ] Width < 100 → tabs; `Tab` switches tree ↔ diff; comment bar
      collapses to 1 line.
- [ ] Live `pilot.resize_terminal(...)` triggers reflow without losing
      selection or comments.
- [ ] Custom `[ui.breakpoints]` values in config are respected.

### 5.2 Watcher (`vcs/watcher.py`)

- [ ] Edit to a tracked file triggers a single reload (events
      debounced ≤ `debounce_ms`).
- [ ] Burst of 20 edits within the debounce window coalesces to one
      reload.
- [ ] `.git/index` change (staging from another terminal) refreshes the
      tree.
- [ ] `.jj/` snapshot write refreshes the tree.
- [ ] `.gitignore` / `.jjignore` / `extra_ignore_globs` paths do NOT
      trigger reloads.
- [ ] Scroll position and expanded folds survive a reload when possible.
- [ ] Manual `r` forces a reload bypassing debounce.
- [ ] `vcs.watch = false` disables the watcher cleanly.

### 5.3 Conflict display

- [ ] Conflict file in the tree renders the `!` badge and the group
      header shows a `(N conflicts)` count.
- [ ] `]c` / `[c` jumps between conflicts.
- [ ] Diff panel for a conflict renders **two stacked DiffViews**:
      `BASE ↔ OURS` and `BASE ↔ THEIRS`, each with its own pill header.
- [ ] When base is unavailable, single `OURS ↔ THEIRS` block is shown
      with a warning pill.
- [ ] Commenting inside the `BASE ↔ OURS` block tags side
      `OURS` (or `BASE`) in the exported prompt.
- [ ] Commenting inside `BASE ↔ THEIRS` tags `THEIRS` (or `BASE`).

### 5.4 End-to-end review flow

- [ ] User navigates to a file, selects 2 lines, presses `c`, types a
      message, submits; the comment appears in the list with correct
      side.
- [ ] User adds comments across 3 files spanning LEFT / RIGHT /
      hunk-level; pressing `y` yields a prompt that round-trips through
      a markdown parser and contains all three entries with correct
      labels.
- [ ] Restart (`q` then relaunch) does NOT persist comments (in-session
      only for v0.1/v0.2).

---

## 6. Visual regression (`pytest-textual-snapshot`)

Each scenario is a small script under `tests/scenarios/` that builds a
deterministic state, then `snap_compare` renders an SVG.

- [ ] `wide_layout_git.svg` — tree + split diff + comment bar at 140x40.
- [ ] `wide_layout_jj.svg` — same but with jj graph chars `@ ◆ ○ │`.
- [ ] `medium_unified.svg` — tree + unified at 120x30.
- [ ] `narrow_tabs_tree.svg` — tree tab at 80x24.
- [ ] `narrow_tabs_diff.svg` — diff tab at 80x24.
- [ ] `fold_collapsed.svg` — diff with a `236 hidden lines ▾` marker.
- [ ] `fold_expanded.svg` — same after clicking the marker.
- [ ] `comment_focused.svg` — comment bar focused, anchor prefilled.
- [ ] `comment_list_populated.svg` — 3 comments visible in the list.
- [ ] `conflict_stacked.svg` — conflict file with two stacked DiffViews.
- [ ] `conflict_no_base.svg` — single OURS↔THEIRS block with warning.
- [ ] `stale_comment.svg` — dimmed `(stale)` comment after re-anchor.
- [ ] `transparent_background.svg` — confirms no solid backdrop on
      Screen (for theme = `textual-ansi`).
- [ ] `overlay_help.svg` — help overlay is the only solid surface.

---

## 7. Smoke (CI-only, tmux)

Marked `@pytest.mark.smoke`; run via `pytest -m smoke` in CI only.

- [ ] `dff` launches in a real PTY against a git fixture repo and
      `q` exits cleanly (non-zero exit = failure).
- [ ] Same against a jj fixture repo.
- [ ] Startup time < 500 ms at p95 on fixture repo.

---

## 8. Performance (optional, v0.3+)

- [ ] Rendering a 2000-line file fits in 200 ms (benchmark).
- [ ] Watcher event → UI reload ≤ 250 ms including debounce.
- [ ] 500 files in a single change renders the tree without blocking
      input handling.

---

## Appendix: fixture helpers

- [ ] `git_repo(tmp_path)` fixture: inits repo, creates commits, stages
      files, returns root.
- [ ] `jj_repo(tmp_path)` fixture: `jj init --git`, creates a few
      changes, returns root.
- [ ] `conflict_git_repo(tmp_path)` fixture: produces a guaranteed
      unmerged state.
- [ ] `conflict_jj_repo(tmp_path)` fixture: produces a first-class
      conflict commit.
- [ ] `FakeBackend` for pure widget tests without shelling out.
