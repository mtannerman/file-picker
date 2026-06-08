# file-picker

A small terminal (curses) UI for browsing a directory tree, marking files, and
printing a single Markdown bundle of their contents to standard output. Handy
for assembling code context to paste into an LLM, a code review, or a gist.

Mark a file or folder as **full** (its contents are included in a fenced code
block) or **reference** (only the path is listed). Folder marks are inherited
by everything inside them, and you can override individual files underneath.

Pure Python standard library — **no dependencies**. Works on Linux and macOS.

## Install

Install with [`uv`](https://docs.astral.sh/uv/), which puts the tool in its own
isolated environment and on your `PATH`.

### From GitHub

```bash
uv tool install git+https://github.com/mtannerman/file-picker.git
```

### From a local clone

```bash
git clone https://github.com/mtannerman/file-picker.git
cd file-picker
uv tool install .
```

## Usage

Run it inside the directory you want to browse:

```bash
filepicker            # opens the picker; on "Generate & Quit" it prints Markdown
filepicker --previous # reprint the last selection without opening the UI
filepicker --help
```

Output goes to stdout, so you can pipe or redirect it:

```bash
filepicker > context.md
filepicker | pbcopy          # macOS: copy to clipboard
filepicker | xclip -sel clip # Linux/X11
```

### Keys

| Key            | Action                                  |
| -------------- | --------------------------------------- |
| `↑` / `↓`      | Move cursor                             |
| `→` / `Enter`  | Open folder                             |
| `←`            | Go to parent folder                     |
| `Space`        | Toggle **full** (include contents)      |
| `f` / `r`      | Toggle **reference** (path only)        |
| `p`            | Peek at a file or folder listing        |
| `h`            | Show the key help                       |
| `g`            | Generate Markdown and quit              |
| `q`            | Quit without generating                 |

When you generate, the selection is saved to `.file_picker_last` in the
directory you launched from, so `filepicker --previous` can replay it.

## Development

```bash
uv sync
uv run filepicker --version
```

You can also run it without installing: `uv run python -m filepicker`.

## License

MIT — see [LICENSE](LICENSE).
