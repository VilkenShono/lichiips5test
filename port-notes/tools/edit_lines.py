"""Line-range edits with checks. Usage inside a script:

    from edit_lines import apply
    apply(path, [(first, last, 'text the first line must contain', 'text the last line must contain', replacement), ...])

Ranges are 1-indexed, inclusive, numbered in the file as it is before any edit; `replacement` is
the new text for the range ('' deletes it; a non-empty one should end with a newline).
"""
import pathlib


def apply(path, edits):
    path = pathlib.Path(path)
    lines = path.read_text().split('\n')
    previous = len(lines) + 1
    for first, last, head, tail, replacement in sorted(edits, key=lambda e: -e[0]):
        assert first <= last < previous, f"overlapping or unordered range {first}-{last}"
        assert head in lines[first - 1], f"line {first}: expected {head!r}, found {lines[first - 1][:120]!r}"
        assert tail in lines[last - 1], f"line {last}: expected {tail!r}, found {lines[last - 1][:120]!r}"
        new = replacement.split('\n')
        if replacement.endswith('\n'):
            new = new[:-1]
        lines[first - 1:last] = new if replacement else []
        previous = first
    path.write_text('\n'.join(lines))
    print(f"{path.name}: {len(edits)} edits applied")
