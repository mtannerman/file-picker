#!/usr/bin/env python3
"""Interactive curses file picker that emits a Markdown bundle of selected files."""
import argparse
import base64
import curses
import os
import sys

from . import __version__

INITIAL_CWD = os.getcwd()
LAST_SELECTION_FILENAME = ".file_picker_last"

# How many bytes to sample when deciding whether a file is text or binary.
_BINARY_SNIFF_BYTES = 8192
# Cap on how many entries a folder peek will list, to stay responsive.
_PEEK_LISTING_CAP = 2000
# Many terminals cap the payload of an OSC 52 clipboard write. xterm's default
# limit is 100000 bytes of *encoded* base64; warn past the safe decoded size.
_OSC52_SAFE_BYTES = 74994


def copy_to_clipboard_osc52(text):
    """Copy text to the local clipboard via the OSC 52 terminal escape sequence.

    This works over SSH and tunnels: the escape sequence rides the terminal
    stream back to the local terminal emulator, which writes to the system
    clipboard. Nothing extra is needed on the remote machine.

    The sequence is written to the controlling terminal (/dev/tty) so that the
    Markdown bundle on stdout can still be piped or redirected. Returns True if
    the sequence was written somewhere the terminal can see it.
    """
    b64 = base64.b64encode(text.encode('utf-8')).decode('ascii')
    seq = f"\033]52;c;{b64}\a"

    # Inside tmux the sequence must be wrapped for passthrough to reach the
    # outer terminal (each ESC is doubled within the DCS passthrough).
    if os.environ.get('TMUX'):
        seq = "\033Ptmux;" + seq.replace("\033", "\033\033") + "\033\\"

    try:
        with open('/dev/tty', 'w') as tty:
            tty.write(seq)
            tty.flush()
        return True
    except OSError:
        # Fall back to stderr, which is usually still the terminal.
        try:
            sys.stderr.write(seq)
            sys.stderr.flush()
            return True
        except OSError:
            return False


def safe_addstr(stdscr, y, x, text, attr=0):
    """addstr that clips to the window and never raises on the bottom corner."""
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    text = text[:max(0, w - x - 1)]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def human_size(num):
    if num < 0:
        return "unknown"
    size = float(num)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            if unit == 'B':
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024


def is_binary_file(path):
    """Heuristic: NUL byte or a high ratio of non-text bytes -> binary."""
    try:
        with open(path, 'rb') as f:
            chunk = f.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return True  # unreadable -> treat as non-previewable
    if not chunk:
        return False  # empty file counts as text
    if b'\x00' in chunk:
        return True
    text_chars = bytes(range(0x20, 0x7f)) + b'\n\r\t\f\b'
    nontext = chunk.translate(None, text_chars)
    return len(nontext) / len(chunk) > 0.30


def get_dir_contents(path):
    """Gets directories and files, sorted and separated."""
    dirs = []
    files = []
    try:
        for item in os.listdir(path):
            # Hide our own bookkeeping file from the picker
            if item == LAST_SELECTION_FILENAME:
                continue
            if os.path.isdir(os.path.join(path, item)):
                dirs.append(item)
            else:
                files.append(item)
    except PermissionError:
        return [], []

    return sorted(dirs), sorted(files)


def effective_mark(path, selected, reference, excluded):
    """Effective mark for a path, honoring folder inheritance and overrides.

    Walks from the path up through its ancestors. The first path with an
    explicit state wins: excluded -> None, selected -> 'F', reference -> 'R'.
    An explicit mark on the path itself therefore overrides an inherited one.
    """
    cur = path
    while True:
        if cur in excluded:
            return None
        if cur in selected:
            return 'F'
        if cur in reference:
            return 'R'
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _has_marked_ancestor(path, selected, reference):
    """True if any strict ancestor of path is marked full or reference."""
    cur = os.path.dirname(path)
    while True:
        if cur in selected or cur in reference:
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def _prune_excluded(selected, reference, excluded):
    """Drop exclusions that no longer sit under any marked folder.

    Such exclusions are redundant (nothing would include the file anyway), and
    keeping them would surprisingly suppress a file if its parent is re-marked.
    """
    stale = {p for p in excluded
             if not _has_marked_ancestor(p, selected, reference)}
    excluded -= stale


def toggle_mark(full_path, target, selected, reference, excluded):
    """Toggle the given mark ('F' full, or 'R' reference) on a path.

    Honors inheritance: if the path already has this *effective* mark, turn it
    off -- recording an explicit exclusion when a parent folder would otherwise
    keep it on. Otherwise set this mark explicitly, clearing the other states.
    """
    if effective_mark(full_path, selected, reference, excluded) == target:
        selected.discard(full_path)
        reference.discard(full_path)
        excluded.discard(full_path)
        # If a marked ancestor would still force it on, pin an exclusion.
        if effective_mark(full_path, selected, reference, excluded) is not None:
            excluded.add(full_path)
    else:
        selected.discard(full_path)
        reference.discard(full_path)
        excluded.discard(full_path)
        (selected if target == 'F' else reference).add(full_path)
    _prune_excluded(selected, reference, excluded)


def draw_menu(stdscr, current_row, current_path, dirs, files,
              selected_files, reference_files, excluded_files):
    """Draws the file browser menu and instructions."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    header = f"Path: {current_path}"
    if len(header) > w - 1:
        header = "..." + header[-(w - 4):]
    safe_addstr(stdscr, 0, 0, header, curses.A_REVERSE)

    combined_list = [f"../"] + [f"{d}/" for d in dirs] + files

    for idx, item_name in enumerate(combined_list):
        if idx >= h - 2:
            break

        if item_name == "../":
            # Navigation entry: not markable, blank gutter for alignment.
            prefix = "    "
        else:
            full_path = os.path.join(current_path, item_name.strip('/'))
            eff = effective_mark(full_path, selected_files,
                                 reference_files, excluded_files)
            if eff == 'F':
                prefix = "[*] " if full_path in selected_files else "(*) "
            elif eff == 'R':
                prefix = "[R] " if full_path in reference_files else "(R) "
            else:
                prefix = "[ ] "

        display_name = f"{prefix}{item_name}"

        if idx == current_row:
            safe_addstr(stdscr, idx + 1, 0, display_name, curses.A_REVERSE)
        else:
            safe_addstr(stdscr, idx + 1, 0, display_name)

    instructions = ("↑/↓: Nav | →/Enter: Open | ←: Back | Space: Full | "
                    "f/r: Ref | p: Peek | h: Help | g: Generate & Quit | q: Quit")
    safe_addstr(stdscr, h - 1, 0, instructions, curses.A_REVERSE)

    stdscr.refresh()


def run_pager(stdscr, title, lines):
    """Full-screen scrollable viewer for a list of text lines."""
    top = 0
    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        body_height = max(1, h - 2)

        header = title
        if len(header) > w - 1:
            header = "..." + header[-(w - 4):]
        safe_addstr(stdscr, 0, 0, header, curses.A_REVERSE)

        for i in range(body_height):
            line_idx = top + i
            if line_idx >= len(lines):
                break
            safe_addstr(stdscr, i + 1, 0, lines[line_idx].replace('\t', '    '))

        footer = "↑/↓/PgUp/PgDn: Scroll | Home/End | q/←/Esc: Back"
        safe_addstr(stdscr, h - 1, 0, footer, curses.A_REVERSE)
        stdscr.refresh()

        max_top = max(0, len(lines) - body_height)
        key = stdscr.getch()
        if key in (ord('q'), 27, curses.KEY_LEFT):
            return
        elif key == curses.KEY_UP:
            top = max(0, top - 1)
        elif key == curses.KEY_DOWN:
            top = min(max_top, top + 1)
        elif key == curses.KEY_NPAGE:
            top = min(max_top, top + body_height)
        elif key == curses.KEY_PPAGE:
            top = max(0, top - body_height)
        elif key == curses.KEY_HOME:
            top = 0
        elif key == curses.KEY_END:
            top = max_top


HELP_LINES = [
    "file-picker keys",
    "",
    "  ↑ / ↓          Move cursor",
    "  → / Enter      Open folder",
    "  ←              Go to parent folder",
    "  Space          Toggle FULL  (include file/folder contents)",
    "  f / r          Toggle REFERENCE  (list path only)",
    "  p              Peek at a file or folder listing",
    "  h              Show this help",
    "  g              Generate Markdown and quit",
    "  q              Quit without generating",
    "",
    "Folder marks are inherited by everything inside them; marking an",
    "individual file underneath overrides the inherited state.",
]


def build_peek_lines(path):
    """Return (title, lines) for previewing a file or folder."""
    rel = os.path.relpath(path, INITIAL_CWD)

    if os.path.isdir(path):
        entries = []
        file_count = 0
        truncated = False
        for root, dirnames, filenames in os.walk(path):
            dirnames.sort()
            for fn in sorted(filenames):
                if fn == LAST_SELECTION_FILENAME:
                    continue
                fp = os.path.join(root, fn)
                entries.append(os.path.relpath(fp, path))
                file_count += 1
                if file_count >= _PEEK_LISTING_CAP:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            entries.append("... (listing truncated)")
        if not entries:
            entries = ["(no files)"]
        title = f"Peek (folder): {rel}"
        return title, [f"{file_count} file(s) under this folder:", ""] + entries

    # It's a file.
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1

    if is_binary_file(path):
        title = f"Peek (binary): {rel}"
        return title, [
            "This file looks binary / not human-readable,",
            "so its contents are not shown here.",
            "",
            f"Path: {rel}",
            f"Size: {human_size(size)}",
        ]

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError as e:
        return f"Peek: {rel}", [f"Could not read file: {e}"]

    lines = content.splitlines() or ["(empty file)"]
    return f"Peek: {rel}", lines


def _picker_loop(stdscr):
    curses.curs_set(0)
    current_row = 0
    current_path = os.getcwd()
    selected_files = set()
    reference_files = set()
    excluded_files = set()

    while True:
        dirs, files = get_dir_contents(current_path)
        combined_list = [f"../"] + [f"{d}/" for d in dirs] + files

        draw_menu(stdscr, current_row, current_path, dirs, files,
                  selected_files, reference_files, excluded_files)

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_row = max(0, current_row - 1)
        elif key == curses.KEY_DOWN:
            current_row = min(len(combined_list) - 1, current_row + 1)
        elif key == curses.KEY_LEFT:
            parent_dir = os.path.dirname(current_path)
            if parent_dir != current_path:
                current_path = parent_dir
                current_row = 0
        elif key == curses.KEY_RIGHT or key == 10:
            selected_item_name = combined_list[current_row].strip('/')
            path_to_open = os.path.join(current_path, selected_item_name)

            if selected_item_name == '..':
                parent_dir = os.path.dirname(current_path)
                if parent_dir != current_path:
                    current_path = parent_dir
                    current_row = 0
            elif os.path.isdir(path_to_open):
                current_path = path_to_open
                current_row = 0
        elif key == ord(' '):
            # Mark as FULL (contents). Works on files and folders.
            name = combined_list[current_row].strip('/')
            if name != '..':
                full_path = os.path.join(current_path, name)
                if os.path.exists(full_path):
                    toggle_mark(full_path, 'F', selected_files,
                                reference_files, excluded_files)
            current_row = min(len(combined_list) - 1, current_row + 1)
        elif key in (ord('f'), ord('r')):
            # Mark as REFERENCE (name only). Works on files and folders.
            name = combined_list[current_row].strip('/')
            if name != '..':
                full_path = os.path.join(current_path, name)
                if os.path.exists(full_path):
                    toggle_mark(full_path, 'R', selected_files,
                                reference_files, excluded_files)
            current_row = min(len(combined_list) - 1, current_row + 1)
        elif key == ord('p'):
            name = combined_list[current_row].strip('/')
            if name != '..':
                full_path = os.path.join(current_path, name)
                if os.path.exists(full_path):
                    title, lines = build_peek_lines(full_path)
                    run_pager(stdscr, title, lines)
        elif key == ord('h'):
            run_pager(stdscr, "Help", HELP_LINES)
        elif key == ord('q'):
            return None
        elif key == ord('g'):
            return (list(selected_files), list(reference_files),
                    list(excluded_files))


def save_last_selection(selected_files, reference_files, excluded_files):
    """Persist the marks in the directory the tool was invoked from."""
    save_path = os.path.join(INITIAL_CWD, LAST_SELECTION_FILENAME)
    try:
        with open(save_path, 'w', encoding='utf-8') as f:
            for p in sorted(selected_files):
                f.write(f"F\t{p}\n")
            for p in sorted(reference_files):
                f.write(f"R\t{p}\n")
            for p in sorted(excluded_files):
                f.write(f"X\t{p}\n")
    except OSError as e:
        print(f"Warning: could not save last selection to {save_path}: {e}",
              file=sys.stderr)


def load_last_selection():
    """Load the previously saved marks, or None if missing.

    Returns a (selected_files, reference_files, excluded_files) tuple.
    """
    load_path = os.path.join(INITIAL_CWD, LAST_SELECTION_FILENAME)
    if not os.path.isfile(load_path):
        print(f"No previous selection found in {INITIAL_CWD}", file=sys.stderr)
        print(f"(Expected file: {load_path})", file=sys.stderr)
        return None
    selected, reference, excluded = [], [], []
    try:
        with open(load_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line.strip():
                    continue
                if '\t' in line:
                    mode, path = line.split('\t', 1)
                else:
                    mode, path = 'F', line   # tolerate the old plain-path format
                if mode == 'R':
                    reference.append(path)
                elif mode == 'X':
                    excluded.append(path)
                else:
                    selected.append(path)
    except OSError as e:
        print(f"Error reading {load_path}: {e}", file=sys.stderr)
        return None
    return selected, reference, excluded


def expand_to_files(paths):
    """Expand a list of paths (files and/or dirs) into a deduped list of files.

    Directories are walked recursively; the bookkeeping file is skipped.
    """
    result = []
    seen = set()
    for p in paths:
        if os.path.isdir(p):
            for root, dirnames, filenames in os.walk(p):
                dirnames.sort()
                for fn in sorted(filenames):
                    if fn == LAST_SELECTION_FILENAME:
                        continue
                    fp = os.path.join(root, fn)
                    if fp not in seen:
                        seen.add(fp)
                        result.append(fp)
        elif os.path.isfile(p):
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


def generate_markdown(selected_files, reference_files, excluded_files,
                      clipboard=False):
    """Reads files and formats them into markdown.

    Every file that resolves to an effective 'full' mark (directly or via a
    marked folder, minus any exclusions) gets its contents in a code block.
    Files resolving to 'reference' get a name-only placeholder line.

    By default the bundle is printed to stdout. When ``clipboard`` is set, it is
    instead sent to the local clipboard via OSC 52 (useful over SSH/tunnels).
    """
    if not selected_files and not reference_files:
        print("No files were selected.", file=sys.stderr)
        return

    selected = set(selected_files)
    reference = set(reference_files)
    excluded = set(excluded_files)

    # Candidate files are everything reachable from a marked root, then each is
    # classified by its effective mark (which applies inheritance + overrides).
    candidates = expand_to_files(list(selected) + list(reference))

    classified = []
    for fp in candidates:
        mode = effective_mark(fp, selected, reference, excluded)
        if mode in ('F', 'R'):
            classified.append((fp, mode))

    if not classified:
        print("No files were selected.", file=sys.stderr)
        return

    output_parts = []
    for file_path, mode in sorted(classified, key=lambda x: x[0]):
        display_path = os.path.relpath(file_path, start=INITIAL_CWD)

        if mode == 'R':
            output_parts.append(
                f"{display_path}\n(File contents not shown. Listed for reference only.)")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            file_name = os.path.basename(file_path)
            lang = os.path.splitext(file_name)[1].lstrip('.')

            output_parts.append(f"{display_path}\n```{lang}\n{content}\n```")
        except Exception as e:
            print(f"Error reading file {file_path}: {e}", file=sys.stderr)

    output = "\n\n".join(output_parts)

    if not clipboard:
        print(output)
        return

    nbytes = len(output.encode('utf-8'))
    if copy_to_clipboard_osc52(output):
        print(f"Copied {len(classified)} file(s) ({human_size(nbytes)}) to the "
              "clipboard via OSC 52.", file=sys.stderr)
        if nbytes > _OSC52_SAFE_BYTES:
            print("Warning: output is large; some terminals cap OSC 52 "
                  f"clipboard writes (~{human_size(_OSC52_SAFE_BYTES)}) and may "
                  "truncate or ignore it.", file=sys.stderr)
    else:
        print("Could not reach a terminal to send the OSC 52 sequence; "
              "printing to stdout instead.", file=sys.stderr)
        print(output)


def main(argv=None):
    """Console-script entry point."""
    parser = argparse.ArgumentParser(
        prog="file_picker",
        description="Browse files in a terminal UI, mark them, and print a "
                    "Markdown bundle of their contents to stdout.")
    parser.add_argument(
        "--previous", action="store_true",
        help="Skip the UI and regenerate output from the last saved selection "
             f"({LAST_SELECTION_FILENAME}) in the current directory.")
    parser.add_argument(
        "-c", "--clipboard", action="store_true",
        help="Copy the Markdown bundle to your local clipboard via OSC 52 "
             "instead of printing it. Works over SSH/tunnels, provided your "
             "local terminal has clipboard writes enabled.")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    # Replay mode: regenerate from the last saved selection.
    if args.previous:
        result = load_last_selection()
        if result:
            selected_files, reference_files, excluded_files = result
            generate_markdown(selected_files, reference_files, excluded_files,
                              clipboard=args.clipboard)
        return 0

    try:
        result = curses.wrapper(_picker_loop)
        if result and (result[0] or result[1]):
            selected_files, reference_files, excluded_files = result
            save_last_selection(selected_files, reference_files, excluded_files)
            generate_markdown(selected_files, reference_files, excluded_files,
                              clipboard=args.clipboard)
    except curses.error as e:
        print(f"Curses error: {e}", file=sys.stderr)
        print("Your terminal might not support curses.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
