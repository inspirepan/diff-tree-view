# diff-tree-view

一个为 **jujutsu** 和 **git** 设计的终端 UI diff 查看器，灵感来自 VS Code 中的 VCS 面板。在仓库目录下运行 `dff`，即可获得交互式、键盘驱动的代码审查体验 — 左侧文件树，右侧富文本 diff，底部内联注释，可复制为 Claude 的 prompt。

状态：**规划阶段 / 预发布**。本 README 同时作为路线图。

---

## 为什么需要它

`jj diff` 和 `git diff` 很好用，但在分页器中审查多文件变更意味着要滚动浏览平铺的输出，没有结构。现有的 TUI 工具如 `lazygit` 和 `jjui` 在分支/变更操作上很强大，但将 diff 审查视为次要功能。`dff` 则相反：它是一个**专门的 diff 审查工具**，拥有文件树、可折叠的未变更区域、双列 (side-by-side) / 统一 (unified) 模式、响应式布局，以及类 PR 的评论流程。

---

## 功能

### 视觉设计

美学风格参考 [`jjui`](https://github.com/idursun/jjui) 和其他极简主义 CLI（zellij、starship）：**没有 Unicode 框边框，没有"框式按钮"组件**。区域仅通过三种方式分隔 —

1. **背景色差** — 一个面板的边界是一条细 `$surface` 条纹覆盖透明终端背景，而不是 `┌─┐` 风格的盒子。
2. **反色 "pill" 标签** — 部分标题、模式指示器和单个彩色按钮（`[ copy ]`）渲染为实心背景、带内边距的文本（`background: $primary; color: $background; padding: 0 1`），而不是有边框的组件。
3. **内联符号** — jj 风格的图形字符（`@`、`◆`、`○`、`│`、`├`、`└`）用于变更树；`▸` / `▾` 用于注释条目和折叠标记；中点 `·` 作为状态栏分隔符。

具体来说，在 TCSS 中：所有内容默认获得 `border: none;`，没有 `Static` 被包装在 `Container` 中仅为了获得轮廓，整个 chrome 都在透明背景的故事范围内 — 除了 pill 和浮层下，终端壁纸都会透过来。

宽屏布局（终端宽度 `>= 140`），完整审查会话：

```
 CHANGES                                 src/app.py  M +12 -3                split
 @  xmzynnxm  tidy logs                  ────────────────────────────────────────
 │    M  src/app.py     +12 -3            10  def setup():      │ 10  def setup():
 │    M  src/cli.py     +5  -2            11-   import os       │
 │    A  tests/test.py  +25               12-   import sys      │ 12+ import pathlib
 ○  4f2c6a  refactor parser              ··· 236 hidden lines ▾ ···················
 ○  8b1d9e  wip: notes                   250  def main():       │ 250 def main():
 ◆  root()                                 …

 COMMENTS  2                                                             [ copy ]
 ▸ src/app.py   R11-12  pathlib would be more consistent?
 ▸ src/cli.py   L40     missing try/except around subprocess

 comment  ›  src/app.py R11-12 (RIGHT, added)          Enter submit · Esc cancel
 ›  pathlib would be more consistent?_

 dff   ↑↓ nav  ·  space select  ·  c comment  ·  y copy  ·  m mode  ·  ? more  ·  q quit
```

关于这个 mockup 的说明：

- `CHANGES`、`src/app.py ... split`、`COMMENTS 2`、`comment` 和 `dff` 是 **pill** — 实心背景、内边距文本、无边框。
- 唯一的水平线（`────`）是单行 `Rule`/`Static`，着色为 `$foreground 20%`；它是可选的且可以隐藏。
- 树和 diff 之间的面板分隔是 1 列间隙加一条微弱的 `$surface 50%` 条纹 — 不是竖直的 `│`。
- 树中的 `@ ◆ ○ │` 是 jj 图形字符，直接打印。git 模式用 `●` 代替 `Staged` 和 `○` 代替 `Unstaged`。
- 状态栏提示之间的中点 `·`，着色为 `$foreground 40%`。

### VCS 后端

- **jujutsu** — 显示从 trunk 到 `@` 的变更链（默认 revset `trunk()..@`，可配置）。每个变更在树中都是一个分组。
- **git** — 显示 `Staged` 和 `Unstaged` 分组，各自拥有文件列表。
- 根据 `.jj` / `.git` 在仓库中的存在自动检测使用哪个后端。
- 可通过 `--backend jj|git` 或配置显式覆盖。

### 变更树（左面板）

- 分组：
  - jj：revset 范围内每个变更一个分组。
  - git：`Staged` 和 `Unstaged`。
- 文件嵌套在**真实目录树**下（如 VS Code Explorer），单子目录可选折叠。
- 逐文件徽章：`M` / `A` / `D` / `R` 状态和 `+N -N` 行统计。
- 逐分组摘要：文件计数和聚合 `+N -N`。
- 基于 glob 的忽略列表（锁文件、`dist/**` 等显示但去强调）。
- 键盘导航：`j/k` 或箭头键，`J/K` 用于下一个/上一个变更。

### Diff 查看（右面板）

基于 [`textual-diff-view`](https://github.com/batrachianai/textual-diff-view) 构建。

- **双列** (side-by-side) 和**统一** (unified) 模式，可用 `m` 切换。
- **自动换行**用于长行（`DiffView` 原生支持，split 和 unified 两种模式都有专用的换行/无换行组合路径）；运行时用 `w` 切换，默认从 `ui.word_wrap` 获取。
- **字符级 diff 高亮**在 `replace` hunk 内 — 变更的子字符串着色强度更高于行级背景，让你清晰看到行的哪部分改动了。`DiffView` 原生支持。
- **语法高亮**通过 Textual 的 `highlight` 模块（语言从文件名自动检测）。
- **主题感知** — 跟随活跃 Textual 主题（默认：`textual-ansi`），新增/删除/装订线颜色与终端调色板匹配。
- **透明背景** — 应用默认使用 `textual-ansi` 并将 `Screen` 和所有主容器设置为 `background: transparent`，终端自身的背景（包括任何半透明终端效果）会显示出来。仅浮层（完成弹窗、帮助、确认对话框）保持实心 `$surface` 背景。可通过 `ui.transparent = false` 关闭。
- **可折叠的未变更区域**（VS Code 风格）：连续的未变更行折叠为 `N hidden lines` 标记；点击或按 `Enter` 展开。上下文大小和"如果较小则始终展开"阈值可配置。
- 分列模式下同步滚动。
- 来自 `before` 和 `after` 两侧的行号。

### 实时自动刷新（文件监听器）

变更树和当前打开的 diff 都保持**实时**更新。编辑、暂存或在另一个终端运行 `jj`/`git` 命令后，无需退出再重启 `dff`。

- 后台监听器（基于 [`watchfiles`](https://github.com/samuelcolvin/watchfiles)，Rust 后端，asyncio 原生）观察：
  - **工作区**（尊重 `.gitignore` / `.jjignore`）— 捕获对已追踪文件的编辑。
  - **`.git/index`**、**`.git/HEAD`**、`.git/refs/**` — 捕获 `git add`、提交、分支切换。
  - **`.jj/`** 内部状态 — 捕获 `jj squash`、`jj new`、`jj abandon`、工作副本快照变更。
- 事件被**防抖**（默认 150 ms），这样一连串写入仅触发一次重新加载。
- 事件时：重新运行后端的 `list_changes()` + 刷新统计；如果当前选中文件改变，就地重新渲染其 diff。滚动位置和展开折叠区域集合在刷新时尽可能保留。
- 注释在刷新时**不会**清除。已存储注释中的行号通过新的 hunk map 重锚定；如果注释范围在刷新后不再存在，标记为 `stale`（变淡，仍可复制）。
- 手动 `r` 仍可强制重新加载。
- 通过 `[vcs] watch = false` 禁用，或通过 `[vcs.watch] debounce_ms` 和 `[vcs.watch] extra_ignore_globs` 调优。

### 响应式布局

如同响应式网页，`dff` 根据终端宽度自动重排：

| 宽度          | 布局                                         |
|--------------|----------------------------------------------|
| `>= 140`     | 树 + **分列** (split) diff + 评论栏          |
| `100 – 140`  | 树 + **统一** (unified) diff + 评论栏        |
| `< 100`      | 单面板，`Tab` 切换树 / diff                   |

断点可配置。

### 行选择与评论

PR 审查工作流，不离开终端。

#### LEFT vs RIGHT（你正在评论的是哪一侧）

每条注释都锚定到一个 **side**，与 GitHub / GitLab / Gerrit / Sublime Merge 如何建模审查注释一致：

- **LEFT** = 被删除的 / before 版本（`-` 行展示的内容）。
- **RIGHT** = 被添加的 / after 版本（`+` 行展示的内容）。
- 跨越同一 hunk 两侧的注释标记为 `hunk-level`。

side 如何确定：

- **分列模式**：被聚焦的列。`h` / `l`（或 `Tab`）切换列焦点；点击一列会聚焦它。
- **统一模式**：由行前缀确定 — `-` → LEFT，`+` → RIGHT。对于上下文行（` `），默认 side 是 RIGHT（通常的"评论新代码"意图）；在打开注释前按 `[` 强制 LEFT，按 `]` 强制 RIGHT。

选择必须属于单一 side。如果在分列模式中跨 side 拖拽，`dff` 会询问是否将其分为两条注释或中止（`comment.cross_side = ask | split | reject`）。

#### 用户流程

1. **选择** — 鼠标点击拖拽，或 `Space` 开始/扩展行选择（`Shift+↑/↓` 增长）。装订线显示实时标签如 `L11-12 (LEFT, removed)` 或 `R8-11 (RIGHT, added)`。
2. **按 `c`** — 底部评论栏获得焦点，预填充锚点：`src/app.py R8-11 (RIGHT, added)`。
3. **输入** — `Enter` 提交（添加到会话内 `CommentStore`），`Shift+Enter` 或 `Ctrl+J` 插入换行，`Esc` 取消。
4. **管理** — 聚焦注释列表（`g c`），然后 `Enter` 跳转到锚点（打开文件、展开折叠、滚动到行），`e` 编辑，`d` 删除。
5. **导出** — `y`（或点击 `[copy]`）将所有注释序列化为 markdown prompt 并放到剪贴板。
6. **实时重锚定** — 当监听器刷新时，每条注释通过新的 hunk map 使用 `(side, line_range, content_hash)` 重锚定。移位自动跟随；如果注释内容不再存在，注释标记为 `stale`（变淡）。

#### 导出 prompt 格式

设计上让 Claude 理解 LEFT / RIGHT 区别不存在歧义 — side 标签被拼写出来，引用的行是真正的 fenced `diff` 代码块：

```markdown
# Code review comments for z9a7 "tidy logs"

> Diff sides: **LEFT** = removed (before), **RIGHT** = added (after).

## src/app.py

### L8-10 (LEFT, removed)
```diff
- import os
- import sys
- from pathlib import Path
```
> Why not drop the whole block?

### R9-11 (RIGHT, added)
```diff
+ import pathlib
+ from typing import Annotated
```
> Does the typing import belong here?

### L9-10 ↔ R8-11 (hunk-level)
> Overall refactor is fine but please split into two commits.
```

代码片段是否嵌入（fenced `diff` 代码块）由 `comment.include_code_snippet` 控制。整个模板可通过 `comment.templates.custom.path`（Jinja）覆盖。

### 配置

TOML，加载顺序如下（后者覆盖前者）：

1. 内置默认值
2. `~/.config/dff/config.toml`
3. `./.dff.toml`（项目本地）
4. 环境变量（`DFF_UI_THEME=...`）
5. CLI 标志

可配置区域：

- **`[ui]`** — 主题、默认 diff 模式、自动换行、行号、语法高亮开/关、透明背景开/关、响应式断点。
- **`[fold]`** — 启用、上下文行、"如果较小则始终展开"阈值。
- **`[tree]`** — 按变更或目录分组、显示统计、折叠单子目录、忽略 glob。
- **`[vcs.jj]`** — 默认 revset、`--ignore-working-copy`、`@` 是否作为自己的行。
- **`[vcs.git]`** — 显示已暂存/未暂存、是否合并为一个"Working"分组。
- **`[performance]`** — 降级到纯文本前的最大文件行数、每个变更的最大文件数、并行子进程数。
- **`[vcs.watch]`** — 启用、防抖间隔 (ms)、额外忽略 glob、是否监听 `.git/` 和 `.jj/` 内部状态。
- **`[comment]`** — 剪贴板 vs 文件导出、prompt 中包含代码片段、自定义 Jinja prompt 模板、`cross_side` 行为（`ask | split | reject`）、默认上下文行 side（`context_side = right | left`）。
- **`[keys]`** — 每个按键绑定都可重新绑定。
- **`[integrations]`** — `$EDITOR` 用于 `e` 键。

项目随附完整注释的 `config.example.toml`。

### 按键绑定（默认）

| 按键      | 动作                                |
|-----------|---------------------------------------|
| `j` / `k` | 树中下一个/上一个项目                 |
| `J` / `K` | 下一个/上一个变更分组                 |
| `Enter`   | 展开树节点 / 折叠区域                |
| `Space`   | 切换行选择（diff）                   |
| `[` / `]` | 强制注释 side 为 LEFT / RIGHT（上下文行） |
| `h` / `l` | 切换聚焦列（分列模式）               |
| `c`       | 在当前选择上开始评论                  |
| `g c`     | 聚焦注释列表                         |
| `Esc`     | 取消评论输入 / 清除选择              |
| `y`       | 复制所有注释为 prompt                 |
| `m`       | 切换分列 / 统一                      |
| `Tab`     | （窄屏）切换树 ↔ diff 面板           |
| `r`       | 强制刷新（通常自动）                  |
| `w`       | 切换自动换行                         |
| `e`       | 在 `$EDITOR` 中打开当前文件          |
| `?`       | 帮助浮层                             |
| `q`       | 退出                                 |

---

## 安装

需要 Python 3.14+。

```bash
uv tool install diff-tree-view  # once published
# or for development:
uv sync
uv run dff
```

运行时依赖：`textual`、`textual-diff-view`、`watchfiles`、`pyperclip`。

---

## 用法

```bash
dff                          # auto-detect jj or git, show default revset
dff --rev 'trunk()..@'       # explicit jj revset
dff --backend git            # force git
dff --rev HEAD~3..HEAD       # git rev range
dff --staged                 # git staged only
dff --mode unified           # override default diff mode
```

在 TUI 中，按 `?` 查看完整按键映射。

---

## 架构

```
src/diff_tree_view/
  cli.py                       CLI entry; arg parsing; backend detect
  app.py                       Textual App; composes tree/diff/comment bar
  layout.py                    Responsive breakpoint logic
  config.py                    TOML loader + dataclasses

  vcs/
    base.py                    Protocol: Backend / Change / FileChange
    detect.py                  Picks jj vs git
    jj.py                      subprocess: jj log / diff --summary / file show
    git.py                     subprocess: git diff --name-status / show
    watcher.py                 watchfiles-based async watcher; debounced
                               events fed to App.refresh_from_vcs()

  widgets/
    change_tree.py             Tree widget with VS Code-style grouping
    diff_panel.py              Wraps CollapsibleDiffView + header
    collapsible_diff.py        Extends DiffView with fold/expand
    line_selection.py          Mouse + keyboard line selection
    comment_bar.py             Bottom input + comment list + copy
    status_bar.py

  app.tcss                     Global stylesheet. Rules:
                               * {border: none} everywhere; transparent
                               backgrounds on Screen + containers;
                               `.pill` / `.pill.-accent` / `.pill.-dim`
                               for reverse-color labels; `$surface` only
                               on overlays (help, confirms, popups).

  models/
    change.py                  Change, FileChange, HunkStats
    comment.py                 Comment(file, side, line_range, body,
                               content_hash), CommentStore + re-anchor

  prompt.py                    CommentStore -> markdown prompt
```

### 透明背景 — 工作原理

三个部分组合：

1. **主题** — `app.py` 中的 `App.theme = "textual-ansi"`。ANSI 主题将调色板决策保持在终端侧，而不是强制浅/深表面。
2. **全局 TCSS** — 在 `app.tcss` 中，`Screen` 和所有布局容器（`#tree-panel`、`#diff-panel`、`#comment-bar`、`#status-bar` 等）都声明为 `background: transparent`。内部富文本小部件（`MarkdownFence`、表格、滚动条轨道）也是透明的，这样它们不会重绘自己的背景。
3. **浮层保持不透明** — 帮助、注释列表弹窗、确认对话框使用 `background: $surface`，这样读起来像真正的浮动面板。

`DiffView` 的 `.diff-group` 有一个微妙的 `$foreground 4%` 着色，**通过透明度保留** — 它在终端背景上显示为细微的色彩，这正是我们想要的。已添加/删除行保持其 `$success 10% / $error 10%` 覆盖，设计如此。

### VCS 命令速查表

**jj**

- revset 中的变更：
  `jj log -r '<revset>' --no-graph --ignore-working-copy -T '<template>'`
- 变更中的文件及状态：
  `jj diff -r <id> --summary --ignore-working-copy`
- 文件内容（前/后）：
  `jj file show -r <id>- <path>` / `jj file show -r <id> <path>`

**git**

- 已暂存文件列表：`git diff --cached --name-status`
- 未暂存文件列表：`git diff --name-status`
- 内容：
  - `HEAD:<path>`（已暂存前）/ `:<path>`（已暂存索引）/ worktree 文件（未暂存后）

---

## 路线图

### v0.1 — MVP

- [ ] 项目脚手架 (uv, Textual app skeleton, CLI)
- [ ] VCS 后端抽象 + 自动检测
- [ ] jj 后端（只读）
- [ ] git 后端（只读）
- [ ] 带统计和 M/A/D/R 的变更树小部件
- [ ] 集成 `textual-diff-view`（分列 + 统一，换行切换）
- [ ] 响应式布局（分列 / 统一 / 标签）
- [ ] 文件监听器 (`watchfiles`) 自动刷新树 + diff
- [ ] 最小配置：`[ui]`、`[vcs.jj.revset]`、`[vcs.watch]`、`[keys]`、`[comment.clipboard]`

### v0.2 — 审查工作流

- [ ] 可折叠未变更区域（扩展 `DiffView`）
- [ ] 行选择（鼠标 + `Space`）
- [ ] 带会话内存储的评论栏
- [ ] 复制为 prompt（markdown，剪贴板）
- [ ] 自定义 Jinja prompt 模板
- [ ] `[fold]`、`[performance]` 配置章节

### v0.3 — 打磨

- [ ] 在编辑器中打开 (`e`)
- [ ] 帮助浮层 (`?`)
- [ ] 忽略 glob 并去强调渲染
- [ ] 大文件降级（纯文本，无高亮）
- [ ] 刷新 (`r`) 无需重新加载应用

### 之后

- [ ] 注释写支持（持久化到 `.dff/reviews/*.md`）
- [ ] 监听模式（文件变更时自动刷新）
- [ ] 跳转到 jj 中的父变更 / 子变更
- [ ] 注释内联渲染于 diff 旁边（不仅底部）

---

## 非目标

- **不是 VCS 操作工具。** 无提交、压缩、变基、推送。使用 `jj`、`git`、`jjui` 或 `lazygit`。`dff` 仅限只读审查。
- **不是合并冲突解决器。**
- **不是 PR 客户端。** `dff` 不了解 GitHub / GitLab。它仅产生可粘贴到其他地方的 prompt / markdown。

---

## 开发

```bash
uv sync
uv run dff                   # run against current repo
uv run pytest                # tests
uv run ruff check .
uv run ruff format .
```

---

## 致谢

- [`textual`](https://github.com/Textualize/textual) — TUI 框架。
- [`textual-diff-view`](https://github.com/batrachianai/textual-diff-view) —
  diff 渲染小部件。
- [`jjui`](https://github.com/idursun/jjui) — 如何从 TUI 驱动 `jj` 的参考。
- VS Code — 文件树和内联折叠标记的 UX 参考。

---

## 许可证

待定。

---

> 本文档由英文版翻译而来，若有歧义以 [README.md](./README.md) 为准。
