"""Mirrors the port repository with instrumented CMake files, so every text anchor of the
generated-source rules reports when it no longer matches the emulator source.

Usage: python3 -I cmake_instrument.py <port repo> <mirror dir>

Every `string(REPLACE match ...)`, `string(FIND ... needle var)` and `file(READ path var)` in
headless/**/*.cmake and headless/CMakeLists.txt gets a check that calls __harness_miss(kind file
line text) when the anchor is absent. The driver (cmake_harness.cmake) defines __harness_miss.
"""
import os
import hashlib
import pathlib
import re
import shutil
import sys

port, mirror = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
# Probes that choose between two versions of the emulator source: a miss is an answer, not a fault.
VARIANT_PROBES = ('const auto& last_segment = nso_header.segments.back();', '${eden_fp_dmb_translate}',
                  '${pipeline_wait_old}')


def tokenize(text):
    """Yields (name, args, start, end, line): args are raw argument texts, [start, end) the span."""
    i, n = 0, len(text)
    ident = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
    bracket_open = re.compile(r'\[(=*)\[')
    while i < n:
        c = text[i]
        if c == '#':
            m = bracket_open.match(text, i + 1)
            if m:
                close = text.find(']' + m.group(1) + ']', m.end())
                i = n if close < 0 else close + len(m.group(1)) + 2
            else:
                j = text.find('\n', i)
                i = n if j < 0 else j
            continue
        m = ident.match(text, i)
        if not m:
            i += 1
            continue
        name, start = m.group(0), i
        j = m.end()
        while j < n and text[j] in ' \t':
            j += 1
        if j >= n or text[j] != '(':
            i = m.end()
            continue
        # Parse the argument list.
        j += 1
        depth, args, current = 1, [], None
        while j < n and depth:
            c = text[j]
            if c == '#' and current is None:
                mb = bracket_open.match(text, j + 1)
                if mb:
                    close = text.find(']' + mb.group(1) + ']', mb.end())
                    j = close + len(mb.group(1)) + 2
                else:
                    k = text.find('\n', j)
                    j = n if k < 0 else k
                continue
            if c == '"':
                k = j + 1
                while k < n and text[k] != '"':
                    k += 2 if text[k] == '\\' else 1
                piece = text[j:k + 1]
                current = piece if current is None else current + piece
                j = k + 1
                continue
            mb = bracket_open.match(text, j) if (c == '[' and current is None) else None
            if mb:
                close = text.find(']' + mb.group(1) + ']', mb.end())
                args.append(text[j:close + len(mb.group(1)) + 2])
                j = close + len(mb.group(1)) + 2
                continue
            if c in ' \t\r\n;':
                if current is not None:
                    args.append(current)
                    current = None
                j += 1
                continue
            if c == '(':
                depth += 1
                if current is not None:
                    args.append(current)
                    current = None
                args.append('(')
                j += 1
                continue
            if c == ')':
                depth -= 1
                if current is not None:
                    args.append(current)
                    current = None
                if depth:
                    args.append(')')
                j += 1
                continue
            if c == '\\' and j + 1 < n:
                current = (current or '') + text[j:j + 2]
                j += 2
                continue
            current = (current or '') + c
            j += 1
        yield name, args, start, j, text.count('\n', 0, start) + 1
        i = j


def instrument(path, relative):
    text = path.read_text()
    out, last = [], 0
    for name, args, start, end, line in tokenize(text):
        lowered = name.lower()
        where = f'"{relative}" {line}'

        def ident(raw):
            return relative + '#' + hashlib.sha1(raw.encode()).hexdigest()[:10]
        if lowered == 'string' and args and args[0] == 'REPLACE' and len(args) >= 5:
            match, inputs = args[1], args[4:]
            before = (f'string(CONCAT __h_in {" ".join(inputs)})\n'
                      f'string(FIND "${{__h_in}}" {match} __h_pos)\n'
                      f'if(__h_pos EQUAL -1)\nstring(SUBSTRING {match} 0 110 __h_needle)\n'
                      f'__harness_miss(REPLACE {where} "{ident(match)}" "${{__h_needle}}")\nendif()\n')
            out.append(text[last:start] + before + text[start:end])
            last = end
        elif lowered == 'string' and args and args[0] == 'FIND' and len(args) >= 4:
            needle, var = args[2], args[3]
            after = (f'\nif({var} EQUAL -1)\nstring(SUBSTRING {needle} 0 110 __h_needle)\n'
                     f'__harness_miss(FIND {where} "{ident(needle)}" "${{__h_needle}}")\n'
                     f'if(HARNESS_FORCE AND NOT "{ident(needle)}" IN_LIST HARNESS_OPTIONAL'
                     f'{" AND FALSE" if any(probe in needle for probe in VARIANT_PROBES) else ""})\nset({var} 0)\nendif()\nendif()\n')
            out.append(text[last:end] + after)
            last = end
        elif lowered == 'file' and args and args[0] == 'READ' and len(args) >= 3:
            source, var = args[1], args[2]
            out.append(text[last:start] + f'if(NOT EXISTS {source})\n__harness_miss(READ {where} "-" {source})\n'
                       f'set({var} "")\nelse()\n' + text[start:end] + '\nendif()\n')
            last = end
        elif lowered == 'configure_file' and len(args) >= 2:
            out.append(text[last:start] + f'if(NOT EXISTS {args[0]})\n__harness_miss(CONFIGURE {where} "-" {args[0]})\n'
                       f'else()\n' + text[start:end] + '\nendif()\n')
            last = end
    out.append(text[last:])
    # Script mode has no configure step to re-run.
    return ''.join(out).replace(' CONFIGURE_DEPENDS ', ' ')


def is_cmake(path):
    return path.name == 'CMakeLists.txt' or path.suffix == '.cmake'


if mirror.exists():
    shutil.rmtree(mirror)
mirror.mkdir(parents=True)
for entry in port.iterdir():
    if entry.name in ('.git', 'headless', 'build', '.local', '.deps'):
        continue
    os.symlink(entry, mirror / entry.name)
count = 0
for directory, subdirs, files in os.walk(port / 'headless'):
    directory = pathlib.Path(directory)
    target = mirror / directory.relative_to(port)
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        source = directory / name
        if is_cmake(source):
            (target / name).write_text(instrument(source, str(source.relative_to(port))))
            count += 1
        else:
            os.symlink(source, target / name)
print(f"instrumented {count} CMake files into {mirror}")
