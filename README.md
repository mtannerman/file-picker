# file-picker

A small terminal (curses) UI for browsing a directory tree, marking files, and
printing a single Markdown bundle of their contents to standard output. Handy
for assembling code context to paste into an LLM, a code review, or a gist.

Mark a file or folder as **full** (its contents are included in a fenced code
block) or **reference** (only the path is listed). Folder marks are inherited
by everything inside them, and you can override individual files underneath.

Pure Python standard library — **no dependencies**. Works on Linux and macOS.

## Install

The recommended way to install a command-line tool is with
[`pipx`](https://pipx.pypa.io/) (or [`uv`](https://docs.astral.sh/uv/)), which
puts it in its own isolated environment and on your `PATH`.

### From GitHub (once you've pushed it)

```bash
pipx install git+https://github.com/mtannerman/file-picker.git
```

or with uv:

```bash
uv tool install git+https://github.com/mtannerman/file-picker.git
```

### From a local clone

```bash
git clone https://github.com/mtannerman/file-picker.git
cd file-picker
pipx install .          # or: uv tool install .
```

### Getting pipx

- **Ubuntu / Debian:** `sudo apt install pipx && pipx ensurepath`
- **macOS (Homebrew):** `brew install pipx && pipx ensurepath`

Open a new shell afterwards so the updated `PATH` takes effect.

> Plain `pip install .` also works, but on recent Ubuntu and Homebrew Python
> it will refuse with an "externally managed environment" error unless you use
> a virtual environment. `pipx`/`uv` avoid that entirely.

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
python -m venv .venv && source .venv/bin/activate
pip install -e .
filepicker --version
```

You can also run it without installing: `python -m filepicker`.

## License

MIT — see [LICENSE](LICENSE).
