# CLAUDE.md — instructions for Claude sessions in this repo

This file is the operating manual for any Claude session working on
**dff**. Read it before doing anything non-trivial. User-visible behavior
and scope are described in [README.md](./README.md); this file is about
**how we build**.

---

## Project

`dff` is a Textual-based terminal UI diff viewer for jujutsu and git. It
is read-only: it reviews, it does not mutate the VCS. Full feature scope
and roadmap live in `README.md`.

---

## Development methodology: TDD

Test-driven, always. For every feature, bug fix, or behavior change:

1. **Find or add the test case** in `docs/testing.md` (the living
   checklist). If the `[ ]` doesn't exist yet, add it under the right
   section first.
2. **Write the test**. Make it fail for the right reason (not an import
   error, not a missing fixture — an actual behavioral assertion).
3. **Implement the minimum** to make the test pass. Resist fattening the
   feature; scope creep is what the roadmap is for.
4. **Run the full test file** (not just the new case) to catch
   regressions. Then run `uv run pytest` once to make sure nothing else
   broke.
5. **Flip the checkbox** in `docs/testing.md` from `[ ]` to `[x]` in the
   same commit as the implementation.
6. **Update snapshots** if a UI change is intentional:
   `uv run pytest --snapshot-update`, then eyeball the resulting SVGs
   under `tests/__snapshots__/` and commit them with the code change.

**Do not** implement first and write tests after. If a refactor has no
behavior change, it needs no new test — but all existing tests must
still pass, and no `[x]` should flip back to `[ ]`.

**Do not** delete a test to make it "pass." If a test is wrong, fix
the test in a dedicated commit with the reason in the message.

---

## Layering and where things live

Keep the layers one-way:

```
cli.py  →  app.py  →  widgets/*  →  models/*
                         ↓            ↑
                      vcs/*  ────────┘
```

- `vcs/` knows nothing about Textual or widgets.
- `models/` is pure data + pure logic (re-anchoring, prompt formatting).
- `widgets/` imports from `models/` and from `textual` / `textual-diff-view`.
- `app.py` wires widgets together and owns the reactive state that
  coordinates them.
- `cli.py` is argument parsing + config loading + backend construction,
  nothing more.

When you're about to reach across a layer (e.g. a widget calling
subprocess directly): stop and add a method on the backend instead.

---

## Stack & tooling

- **Python**: 3.11+ (`tomllib` is stdlib; don't add `tomli`).
- **Package manager**: `uv`, always. Never `pip`, never edit
  `requirements.txt` by hand.
  - Add a dep: `uv add <pkg>`.
  - Add a dev dep: `uv add --dev <pkg>`.
  - Upgrade: `uv add <pkg> --upgrade-package <pkg>`.
- **Framework**: `textual`, `textual-diff-view`, `watchfiles`,
  `pyperclip`.
- **Testing**: `pytest`, `pytest-asyncio`, `pytest-textual-snapshot`.
- **Lint / format**: `ruff` (check + format).

Common commands:

```bash
uv sync                         # install deps
uv run dff                      # launch against the current repo
uv run pytest                   # all tests
uv run pytest -x -k <expr>      # focused run, stop on first fail
uv run pytest --snapshot-update # regenerate SVG snapshots (intentional UI changes)
uv run ruff check .
uv run ruff format .
```

---

## Code style (hard rules)

- **No emoji in code, comments, or docs.** (The terminal target font
  can't be trusted.)
- **English** in code / comments; Chinese is fine in conversation.
- **Comments**: default to none. Only comment when the *why* is
  non-obvious.
- **Imports**: stdlib / third-party / local, blank line between groups,
  `ruff` handles it.
- **Types**: type-annotate public functions and dataclasses. Not
  required on trivial local vars.
- **Errors at boundaries only**: validate user input (CLI flags, config
  TOML) and external outputs (subprocess stdout). Don't wrap internal
  calls in try/except to pre-empt hypothetical failures.
- **No dead code, no `# TODO: remove later`, no `# legacy`**. If it's
  unused, delete it.
- **No backwards-compat shims** before v1.0. We haven't shipped.

## Textual-specific rules

- **Every new widget** gets a CSS entry in `src/dff/app.tcss` with
  `border: none` unless a specific exception is justified. We use
  background shade and `.pill` labels for region separation — see
  "Visual design" in `README.md`.
- **Screen and all layout containers are transparent.** Solid
  `$surface` is only for overlays (help, confirms, popups).
- **Reactive state lives on `App`** when shared across widgets; on the
  widget itself when local. Don't pass mutable state through init args
  — use Textual messages for widget-to-widget communication.
- **Never `await asyncio.sleep`** to wait for UI updates in tests; use
  `await pilot.pause()` or `await pilot.wait_for_animation()`.

---

## File deletion

Use `trash`, not `rm`. Do not trash temporary build artifacts
(`.ruff_cache`, `__pycache__`, `.pytest_cache`, `tests/__snapshots__/*`
during `--snapshot-update` runs); just leave them to gitignore.

---

## Commits

- One logical change per commit.
- Title ≤ 70 chars, imperative: `Add conflict stacked diff rendering`.
- Body explains the *why* when non-obvious. Reference checkbox(es) the
  commit satisfies: `Closes docs/testing.md §5.3 first three boxes.`
- **Do not** commit without running `uv run pytest` locally first.

---

## Checklist before "done"

Before reporting a feature as complete:

- [ ] All new test cases exist and pass.
- [ ] Relevant boxes in `docs/testing.md` flipped to `[x]`.
- [ ] `uv run pytest` is green end to end.
- [ ] `uv run ruff check .` clean.
- [ ] Snapshot SVGs updated and reviewed (if UI changed).
- [ ] README / README.zh.md updated if behavior visible to users changed.
- [ ] No `[ ]` that was `[x]` has been flipped back (= regression).

---

## When stuck

- Textual docs: https://textual.textualize.io/
- `textual-diff-view` is vendored locally at
  `~/code/GITHUB/batrachianai-textual-diff-view` — read its source
  directly rather than guessing.
- `jjui` for idiomatic jj TUI patterns:
  `~/code/GITHUB/idursun-jjui`.
- When `jj` / `git` subprocess behavior is in doubt, run the command in
  a throwaway shell and paste output into the test fixture.

Do not invent behavior. If the right answer isn't obvious from the
code or the linked references, ask.
