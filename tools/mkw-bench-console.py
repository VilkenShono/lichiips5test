#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Repeatable Mario Kart World title benchmark on the console.

Interleaves one or more candidates and variants (A B A B ...), measures the game's presented
frame rate after the intro, the texture collector's device-memory usage, image footprint and the
time to any crash (for example VK_ERROR_OUT_OF_DEVICE_MEMORY), and captures screenshots. A crash
ends that run and is recorded instead of aborting the sequence. The original executable,
settings, save and caches are restored and verified at the end.

  python3 tools/mkw-bench-console.py --host 192.168.0.190 \
    --launcher .local/pipeline-cache/launch-mkw.elf --out .local/bench/NEW_DIR \
    --candidate main=build/main/eboot.bin,build/main/eboot.elf \
    --candidate pr40=CANDIDATE.bin,CANDIDATE.elf \
    --variant 'native|EDEN_NX2_MME_NATIVE=1' --runs 2 --seconds 240

--variant LABEL|NAME=VALUE|...: env.txt lines; '@key=value' sets the title's performance
setting (e.g. @fast_gpu=true). Without --variant one default variant runs.
--events SECONDS:ACTION,...: pad input after the game has loaded (the build must take runner
input: EDEN_SCRIPTED_INPUT=ON, not a development build). ACTION is a button (a, b, lr = L and R
together, plus) with an optional hold in ms (a3000), or shot for a screenshot; e.g.
'35:lr,45:lr,55:a,60:a,...' leaves the title screen and walks the menus into a race.
--cache warm (default) primes the caches once with an unmeasured run, then keeps them;
--cache cold clears them before every run.
Candidates must be input-enabled builds (EDEN_SCRIPTED_INPUT=ON) so runs can return to the
launcher normally. Evidence includes a private settings/save backup: do not publish it.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import sys
import time

helper = Path(__file__).with_name('check-pipeline-cache-console.py')
spec = importlib.util.spec_from_file_location('cache_console', helper)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
helpers = base.helpers
TITLE = base.TITLE.upper()
BUTTONS = {'a': 0x2000, 'b': 0x4000, 'plus': 0x0008, 'lr': 0x0C00}
LOG_FILTER = 'EDEN_LOG_FILTER=*:Warning Render.Vulkan:Info\n'
FRAME = re.compile(r'EDEN_VULKAN_FRAME frames=(\d+) seconds=([\d.]+) fps=([\d.]+) worst_ms=([\d.]+) total=(\d+)')
GC = re.compile(r'MKW_GC frame=(\d+) usage=(\d+) expected=(\d+) critical=(\d+)')
FOOTPRINT = re.compile(r'MKW_IMAGE_FOOTPRINT frame=(\d+) images=(\d+) allocated=(\d+)')
MEMORY = re.compile(r'EDEN_VULKAN_MEMORY .*?device_access=(\d+) capacity=(\d+)')
BREAKDOWN = re.compile(r'EDEN_MEMORY_BREAKDOWN (.*)')


def parse_variant(text):
    label, *items = text.split('|')
    env, perf = [], {}
    for item in filter(None, items):
        key, _, value = item.partition('=')
        if key.startswith('@'):
            perf[key[1:]] = value.lower() == 'true'
        else:
            env.append(key + '=' + value)
    return {'label': label, 'env': env, 'perf': perf}


def analyze(directory, warmup_frames):
    def read(name):
        path = directory / name
        return path.read_text(errors='replace') if path.exists() else ''
    heap, eden = read('heap.log'), read('eden_log.txt')
    windows = [dict(frames=int(a), seconds=float(b), fps=float(c), worst_ms=float(d), total=int(e))
               for a, b, c, d, e in FRAME.findall(heap)]
    steady = [w for w in windows if w['total'] - w['frames'] >= warmup_frames]
    gc = [dict(frame=int(a), usage=int(b), expected=int(c), critical=int(d)) for a, b, c, d in GC.findall(eden)]
    footprint = [dict(frame=int(a), images=int(b), allocated=int(c)) for a, b, c in FOOTPRINT.findall(eden)]
    memory = MEMORY.search(heap)
    result = {
        'windows': len(windows), 'steady_windows': len(steady),
        'steady_seconds': round(sum(w['seconds'] for w in steady), 2),
        'fps_weighted': round(sum(w['frames'] for w in steady) / sum(w['seconds'] for w in steady), 2) if steady else None,
        'fps_median': round(statistics.median(w['fps'] for w in steady), 2) if steady else None,
        'fps_min_window': round(min(w['fps'] for w in steady), 2) if steady else None,
        'worst_ms_median': round(statistics.median(w['worst_ms'] for w in steady), 1) if steady else None,
        'worst_ms_max': round(max(w['worst_ms'] for w in steady), 1) if steady else None,
        'presented_total': windows[-1]['total'] if windows else 0,
        'device_usage_peak_mib': max((g['usage'] for g in gc), default=0) >> 20,
        'collector_critical_mib': gc[-1]['critical'] >> 20 if gc else None,
        'image_footprint_peak_mib': max((f['allocated'] for f in footprint), default=0) >> 20,
        'images_peak': max((f['images'] for f in footprint), default=0),
        'device_access_mib': int(memory[1]) >> 20 if memory else None,
        'breakdown_last': BREAKDOWN.findall(heap + eden)[-1] if BREAKDOWN.search(heap + eden) else None,
        'fps_series': [w['fps'] for w in windows],
    }
    return result


class Bench(base.CacheConsole):
    def __init__(self, args):
        first = args.candidates[0]
        args.candidate, args.elf = first['bin'], first['elf']
        super().__init__(args)
        self.token = 'mkw-bench-' + str(time.time_ns())
        self.active = first['label']
        self.crashes_seen = set()

    def initialize(self):
        super().initialize()
        config = json.loads(self.get(self.data + '/config/eglantineps5.json'))
        self.base_config = config
        index = self.get(self.data + '/logs/crash-index.txt', True) or b''
        self.crashes_seen = set(index.decode(errors='replace').split())
        (self.out / 'settings.json').write_text(json.dumps({
            'performance': config.get('performance'), 'diagnostics': config.get('diagnostics'),
            'video': config.get('video'), 'game': config.get('games', {}).get(TITLE)}, indent=2))

    def deploy(self, candidate):
        if candidate['label'] == self.active:
            return
        self.stop()
        temporary = self.app + '/.' + self.token + '.bin'
        self.put(temporary, candidate['bin'].read_bytes())
        view = self.get(temporary)
        if helpers.load_segments(view) != helpers.load_segments(candidate['elf'].read_bytes()):
            self.remove(temporary)
            raise RuntimeError(candidate['label'] + ': uploaded PT_LOAD segments differ from its ELF')
        if helpers.digest(self.get(self.app + '/eboot.bin')) != self.candidate_hash:
            raise RuntimeError('Executable changed externally during the benchmark')
        self.remove(self.app + '/eboot.bin')
        self.rename(temporary, self.app + '/eboot.bin')
        self.candidate_hash = helpers.digest(view)
        self.active = candidate['label']
        self.log('Deployed ' + candidate['label'] + ' (PT_LOAD verified)')

    def configure(self, variant):
        config = json.loads(json.dumps(self.base_config))
        game = config.setdefault('games', {}).setdefault(TITLE, {})
        game['resolution'] = self.args.resolution
        if variant['perf']:
            game['performance'] = {**game.get('performance', {}), **variant['perf']}
        self.put(self.data + '/config/eglantineps5.json', json.dumps(config, indent=2).encode())
        environment = ''.join(line + '\n' for line in variant['env']) + LOG_FILTER
        self.put(self.app + '/env.txt', environment.encode())
        (self.current / 'env.txt').write_text(environment)
        (self.current / 'game-settings.json').write_text(json.dumps(game, indent=2))

    def clear_caches(self):
        for path, _ in self.caches:
            if self.exists(path):
                self.remove(path)

    def new_crashes(self):
        index = self.get(self.data + '/logs/crash-index.txt', True) or b''
        names = [name for name in index.decode(errors='replace').split() if name not in self.crashes_seen]
        self.crashes_seen.update(names)
        return names

    def boot_line(self):
        data = self.get(self.data + '/logs/boot-trace.txt', True)
        return data.splitlines()[0] if data else b''

    def act(self, action, elapsed):
        if action == 'shot':
            self.screenshot(f'shot-{elapsed:05.0f}s')
            return
        name = re.match(r'[a-z]+', action)[0]
        duration = min(int(action[len(name):] or 200), 3000)
        command = f'{time.time_ns()} {BUTTONS[name]} {duration} 128 128 128 128\n'
        self.put(self.app + '/compat-input.txt', command.encode())

    def measure(self, label, candidate, variant, seconds):
        self.deploy(candidate)
        self.stop()
        self.remove(self.app + '/compat-input.txt')
        self.current = self.out / label
        self.current.mkdir()
        self.configure(variant)
        self.new_crashes()
        before = self.boot_line()
        with socket.create_connection((self.args.host, 9021), timeout=10) as client:
            client.sendall(self.args.launcher.read_bytes())
            client.shutdown(socket.SHUT_WR)
        deadline = time.monotonic() + 90
        while (boot := self.boot_line()) == before:
            if time.monotonic() > deadline:
                raise RuntimeError(label + ': no fresh process boot')
            time.sleep(1)
        self.log(label + ': ' + boot.decode(errors='replace'))
        start = time.monotonic()
        loaded_at = crash = None
        shots = []
        events = list(self.args.events) if label != 'prime' else []
        last_check = 0.0
        while time.monotonic() - start < seconds:
            time.sleep(1 if events and loaded_at is not None else 10)
            elapsed = time.monotonic() - start
            while events and loaded_at is not None and elapsed - loaded_at >= events[0][0]:
                self.act(events.pop(0)[1], elapsed)
            if elapsed - last_check < 10:
                continue
            last_check = elapsed
            crashes = self.new_crashes()
            if crashes or self.boot_line() != boot:
                crash = {'seconds_after_launch': round(elapsed), 'names': crashes}
                break
            self.collect()   # only while the original process lives: restarts truncate logs
            text = (self.current / 'boot.txt').read_text(errors='replace')
            if loaded_at is None and 'game loaded (status 0)' in text:
                loaded_at = elapsed
            if loaded_at is not None and not shots and elapsed - loaded_at >= self.args.shot_after:
                self.screenshot('title')
                shots.append('title')
            if int(elapsed) % 60 < 10:
                heap = (self.current / 'heap.log').read_text(errors='replace')
                frames = FRAME.findall(heap)
                self.log(f'{label} t={elapsed:.0f}s loaded={loaded_at is not None} '
                         f'fps={frames[-1][2] if frames else "-"}')
        if crash:
            time.sleep(5)
            for name in crash['names']:
                for suffix in ('.txt', '-heap.log', '-stderr.log', '-eden_log.txt'):
                    data = self.get(self.data + '/logs/' + name + suffix, True)
                    if data is not None:
                        (self.current / (name + suffix)).write_bytes(data)
                report = self.current / (name + '.txt')
                if report.exists():
                    text = report.read_text(errors='replace')
                    # Errors the app reports carry 'reason:'; signals (SIGABRT, SIGSEGV) only 'what:'.
                    reason = re.search(r'^reason: (.*)$', text, re.M) or re.search(r'^what: (.*)$', text, re.M)
                    crash['reason'] = reason[1] if reason else None
            self.log(f'{label}: crashed at {crash["seconds_after_launch"]} s: {crash.get("reason")}')
            self.screenshot('after-crash')
            self.stop()
        else:
            # Copy the game's logs now: returning to the launcher starts a new process that
            # rewrites them.
            self.collect()
            self.screenshot('end')
            self.pulse(mask=0x100000 | 0x400, duration=500)
            time.sleep(12)
            self.stop()
        result = analyze(self.current, self.args.warmup_frames)
        result.update(label=label, candidate=candidate['label'], variant=variant['label'],
                      loaded_after_s=round(loaded_at) if loaded_at else None, crash=crash,
                      screenshots=sorted(p.name for p in self.current.glob('*.jpeg')))
        (self.current / 'summary.json').write_text(json.dumps(result, indent=2))
        self.log(f'{label}: fps={result["fps_weighted"]} median={result["fps_median"]} '
                 f'usage_peak={result["device_usage_peak_mib"]} MiB images={result["image_footprint_peak_mib"]} MiB '
                 f'crash={crash and crash.get("reason")}')
        return result


def report(results, out):
    lines = ['| Run | FPS (weighted) | Median window | Min window | Worst frame ms (median/max) | '
             'Device peak MiB | Images peak MiB | Crash |', '|---|---|---|---|---|---|---|---|']
    for r in results:
        crash = f'{r["crash"].get("reason")} at {r["crash"]["seconds_after_launch"]} s' if r['crash'] else 'none'
        lines.append(f'| {r["label"]} | {r["fps_weighted"]} | {r["fps_median"]} | {r["fps_min_window"]} | '
                     f'{r["worst_ms_median"]}/{r["worst_ms_max"]} | {r["device_usage_peak_mib"]} | '
                     f'{r["image_footprint_peak_mib"]} | {crash} |')
    groups = {}
    for r in results:
        groups.setdefault((r['candidate'], r['variant']), []).append(r)
    lines += ['', '| Candidate / variant | Runs | FPS median of runs | Crashes | Device peak MiB (max) |',
              '|---|---|---|---|---|']
    for (candidate, variant), runs in groups.items():
        fps = [r['fps_weighted'] for r in runs if r['fps_weighted']]
        lines.append(f'| {candidate} / {variant} | {len(runs)} | '
                     f'{round(statistics.median(fps), 2) if fps else None} | '
                     f'{sum(1 for r in runs if r["crash"])} | {max(r["device_usage_peak_mib"] for r in runs)} |')
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate', action='append', required=True, help='LABEL=SELF.bin,MATCHING.elf')
    parser.add_argument('--variant', action='append', default=[])
    parser.add_argument('--runs', type=int, default=2)
    parser.add_argument('--seconds', type=int, default=240)
    parser.add_argument('--events', default='', type=lambda text: sorted(
        (float(item.partition(':')[0]), item.partition(':')[2]) for item in text.split(',') if item))
    parser.add_argument('--resolution', choices=('0.5x', '0.75x', '1x'), default='0.5x')
    parser.add_argument('--cache', choices=('warm', 'cold'), default='warm')
    parser.add_argument('--warmup-frames', type=int, default=800)
    parser.add_argument('--shot-after', type=int, default=45, help='seconds after load for the title screenshot')
    args = parser.parse_args()
    if os.environ.get('EGLANTINE_CONSOLE_LEASE_HOST') != args.host:
        subprocess.run([sys.executable, str(Path(__file__).with_name('console-lease.py')),
                        '--host', args.host, '--owner', 'mkw-bench', 'run', '--wait', '--',
                        sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], check=True)
        return
    args.candidates = []
    for text in args.candidate:
        label, _, paths = text.partition('=')
        binary, _, elf = paths.partition(',')
        args.candidates.append({'label': label, 'bin': Path(binary), 'elf': Path(elf)})
    variants = [parse_variant(v) for v in args.variant] or [parse_variant('default')]
    console = Bench(args)
    results = []
    try:
        console.initialize()
        if args.cache == 'warm':
            console.measure('prime', args.candidates[0], variants[0], max(150, args.seconds // 2))
        for repetition in range(1, args.runs + 1):
            for candidate in args.candidates:
                for variant in variants:
                    if args.cache == 'cold':
                        console.clear_caches()
                    label = f'{candidate["label"]}-{variant["label"]}-{repetition}'
                    results.append(console.measure(label, candidate, variant, args.seconds))
                    (console.out / 'results.json').write_text(json.dumps(results, indent=2))
                    report(results, console.out)
    finally:
        console.restore()
    print(report(results, console.out))


if __name__ == '__main__':
    main()
