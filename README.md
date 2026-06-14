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
file_picker             # opens the picker; on "Generate & Quit" it prints Markdown
file_picker --previous  # reprint the last selection without opening the UI
file_picker -c          # copy to the local clipboard via OSC 52 (great over SSH)
file_picker --help
```

Output goes to stdout, so you can pipe or redirect it:

```bash
file_picker > context.md
file_picker | pbcopy          # macOS: copy to clipboard
file_picker | xclip -sel clip # Linux/X11
```

### Clipboard over SSH (OSC 52)

`-c` / `--clipboard` sends the Markdown bundle to your **local** clipboard
using the [OSC 52](https://www.rec.se/2018/11/19/copy-to-the-clipboard-with-osc-52/)
terminal escape sequence instead of printing it. The sequence rides the
terminal stream back to your local terminal emulator, so running it on a remote
Ubuntu box reached over SSH or a tunnel lands the output in your MacBook's
clipboard — no extra tooling needed on the remote host. It combines with
`--previous` too (`file_picker --previous -c`).

Notes:

- Your local terminal must allow clipboard writes. iTerm2: *Preferences →
  General → Selection → "Applications in terminal may access clipboard"*.
  tmux is handled automatically (the sequence is wrapped for passthrough); you
  may also need `set -g set-clipboard on` in your tmux config.
- Terminals cap the OSC 52 payload size (~74 KB for the common xterm default);
  very large bundles may be truncated or ignored, and the tool warns when the
  output exceeds that.
- The escape sequence is written to the controlling terminal (`/dev/tty`), so
  stdout stays clean and you can still redirect at the same time if you want.

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
directory you launched from, so `file_picker --previous` can replay it.

## Development

```bash
uv sync
uv run file_picker --version
```

You can also run it without installing: `uv run python -m filepicker`.

## License

MIT — see [LICENSE](LICENSE).
