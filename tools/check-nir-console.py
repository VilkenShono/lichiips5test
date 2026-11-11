#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fresh-cache Bananza NIR comparison with a restored save and shared-console lease.

Requires an input-enabled release twin, its matching native ELF, and a one-shot launcher ELF
built from tools/mkw-title/launch.c with the Bananza base/exefs/main path. No keys/game files
are copied off the console. Evidence includes a private save/config backup: do not publish it.
"""
import argparse
import ftplib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_segments(data):
    if len(data) < 64 or data[:4] != b'\x7fELF' or data[4:6] != b'\x02\x01':
        raise ValueError('Expected a little-endian ELF64 view')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size < 56 or offset + size * count > len(data):
        raise ValueError('Invalid program-header table')
    result = []
    for index in range(count):
        kind, flags, start, address, _, length, memory, align = struct.unpack_from(
            '<IIQQQQQQ', data, offset + size * index)
        if kind == 1:
            if start + length > len(data):
                raise ValueError('Truncated load segment')
            result.append((flags, address, length, memory, align, data[start:start + length]))
    if not result:
        raise ValueError('No loadable segments')
    return (struct.unpack_from('<HH', data, 16), struct.unpack_from('<Q', data, 24)[0], result)


class Console:
    def __init__(self, args):
        self.args = args
        self.app = '/data/homebrew/PPSA98515'
        self.data = '/data/eglantineps5'
        self.token = 'nir-check-' + str(time.time_ns())
        self.out = args.out.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.backups = {}
        self.caches = []
        self.save = None
        self.deployed = False
        self.current = None
        self.generated = []
        self.stop_log = threading.Event()

    def log(self, message):
        print(time.strftime('%H:%M:%S'), message, flush=True)
        with (self.out / 'runner.log').open('a') as output:
            output.write(time.strftime('%H:%M:%S') + ' ' + message + '\n')

    def ftp(self):
        ftp = ftplib.FTP()
        ftp.connect(self.args.host, 2121, timeout=30)
        ftp.login()
        return ftp

    def get(self, path, optional=False):
        try:
            with self.ftp() as ftp:
                data = bytearray()
                ftp.retrbinary('RETR ' + path, data.extend)
                return bytes(data)
        except ftplib.error_perm as error:
            if optional and str(error).startswith('550'):
                return None
            raise

    def put(self, path, data):
        with self.ftp() as ftp:
            ftp.storbinary('STOR ' + path, io.BytesIO(data), blocksize=262144)

    def entries(self, path):
        with self.ftp() as ftp:
            ftp.cwd(path)
            return [(name, facts) for name, facts in ftp.mlsd() if name not in ('.', '..')]

    def exists(self, path):
        try:
            self.entries(path)
            return True
        except ftplib.error_perm:
            return self.get(path, True) is not None

    def rename(self, before, after):
        with self.ftp() as ftp:
            ftp.rename(before, after)

    def remove(self, path):
        try:
            entries = self.entries(path)
        except ftplib.error_perm:
            with self.ftp() as ftp:
                try:
                    ftp.sendcmd('DELE ' + path)
                except ftplib.error_perm as error:
                    if not str(error).startswith('550'):
                        raise
            return
        for name, _ in entries:
            self.remove(path + '/' + name)
        with self.ftp() as ftp:
            ftp.rmd(path)

    def download_tree(self, remote, local):
        local.mkdir(parents=True, exist_ok=True)
        for name, facts in self.entries(remote):
            if facts['type'] == 'dir':
                self.download_tree(remote + '/' + name, local / name)
            else:
                (local / name).write_bytes(self.get(remote + '/' + name))

    def upload_tree(self, local, remote):
        with self.ftp() as ftp:
            try:
                ftp.mkd(remote)
            except ftplib.error_perm:
                pass
        for path in local.iterdir():
            if path.is_dir():
                self.upload_tree(path, remote + '/' + path.name)
            else:
                self.put(remote + '/' + path.name, path.read_bytes())

    def control(self, command):
        with socket.create_connection((self.args.host, 9111), timeout=15) as client:
            client.sendall((command + '\n').encode())
            return client.recv(8192).decode().strip()

    def stop(self):
        state = self.control('status')
        if 'title=PPSA98515' in state:
            self.log(self.control('kill PPSA98515'))
            time.sleep(3)
        elif 'idle' not in state:
            raise RuntimeError('Another application is active: ' + state)

    def initialize(self):
        self.stop()
        for path in [self.app + '/' + name for name in ('env.txt', 'dev-settings.txt', 'compat-input.txt')]:
            self.backups[path] = self.get(path, True)
        config_path = self.data + '/config/eglantineps5.json'
        self.backups[config_path] = self.get(config_path)
        private = self.out / 'private-backup'
        private.mkdir()
        for index, (_, data) in enumerate(self.backups.items()):
            if data is not None:
                (private / str(index)).write_bytes(data)
        self.original_hash = digest(self.get(self.app + '/eboot.bin'))
        temporary = self.app + '/.' + self.token + '.bin'
        self.generated.append(temporary)
        self.put(temporary, self.args.candidate.read_bytes())
        view = self.get(temporary)
        # FTP may decode SELF and change non-loadable signing metadata. Verify every PT_LOAD byte.
        if load_segments(view) != load_segments(self.args.elf.read_bytes()):
            raise RuntimeError('Uploaded executable load segments do not match the candidate')
        self.candidate_hash = digest(view)
        if digest(self.get(self.app + '/eboot.bin')) != self.original_hash:
            raise RuntimeError('Installed executable changed before deployment')
        self.original_eboot = self.app + '/eboot.bin.' + self.token
        self.rename(self.app + '/eboot.bin', self.original_eboot)
        self.deployed = True
        self.rename(temporary, self.app + '/eboot.bin')
        config = json.loads(self.backups[config_path])
        profile = config['profiles']['current']
        save = self.data + '/user/nand/user/save/0000000000000000/' + profile + '/040074A01BF12000'
        if not self.exists(save):
            raise RuntimeError('The required Bananza reference save is absent')
        self.download_tree(save, private / 'save')
        self.save_backup = save + '.' + self.token
        self.rename(save, self.save_backup)
        self.save = save
        for path in [self.data + '/user/cache/shader/040074a01bf12000',
                     self.data + '/user/cache/shader/vulkan_static_pipelines.bin', self.data + '/cache/radv']:
            backup = path + '.' + self.token if self.exists(path) else None
            if backup:
                self.rename(path, backup)
            self.caches.append((path, backup))
        (self.out / 'receipt.json').write_text(json.dumps({
            'candidate_self_sha256': digest(self.args.candidate.read_bytes()),
            'candidate_ftp_elf_sha256': self.candidate_hash,
            'original_sha256': self.original_hash, 'load_segments_verified': True,
            'token': self.token, 'save': self.save, 'save_backup': self.save_backup,
            'caches': self.caches}, indent=2))
        self.thread = threading.Thread(target=self.klog, daemon=True)
        self.thread.start()
        self.log('Candidate deployed and load segments verified')

    def klog(self):
        try:
            with socket.create_connection((self.args.host, 3232), timeout=5) as client, (self.out / 'klog.txt').open('wb') as output:
                client.settimeout(1)
                while not self.stop_log.is_set():
                    try:
                        data = client.recv(65536)
                        if not data:
                            break
                        output.write(data)
                        output.flush()
                    except socket.timeout:
                        pass
        except OSError as error:
            self.log('Kernel capture error: ' + str(error))

    def collect(self):
        if self.current is None:
            return
        for name, remote in [('boot.txt', '/logs/boot-trace.txt'), ('heap.log', '/logs/heap.log'),
                             ('stderr.log', '/logs/stderr.log'), ('eden_log.txt', '/user/log/eden_log.txt'),
                             ('crash-index.txt', '/logs/crash-index.txt')]:
            data = self.get(self.data + remote, True)
            if data is not None:
                (self.current / name).write_bytes(data)

    def screenshot(self, name):
        for _ in range(3):
            for port in (8081, 8080):
                try:
                    url = f'http://{self.args.host}:{port}'
                    image = urllib.request.urlopen(url + '/frame.jpeg', timeout=2).read()
                    if image[:2] == b'\xff\xd8':
                        (self.current / (name + '.jpeg')).write_bytes(image)
                        status = urllib.request.urlopen(url + '/status', timeout=2).read()
                        (self.current / (name + '.capture.json')).write_bytes(status)
                        return
                except OSError:
                    pass
        self.log('No screenshot available: ' + name)

    def pulse(self, mask=8192, duration=200, ly=128):
        command = f'{time.time_ns()} {mask} {duration} 128 {ly} 128 128\n'
        self.put(self.app + '/compat-input.txt', command.encode())
        self.log('Input: ' + command.strip())

    def run(self, mode, repetition):
        self.stop()
        label = f'{mode}-{repetition}'
        self.current = self.out / label
        self.current.mkdir()
        self.upload_tree(self.out / 'private-backup/save', self.save)
        enabled = mode != 'spirv'
        extended = mode == 'expanded'
        environment = (f'EDEN_NX2_NIR={int(enabled)}\nEDEN_NX2_NIR_EXTENDED_COMPUTE={int(extended)}\n'
                       'EDEN_NX2_COMPILE_TIMES=1\nEDEN_NX2_PIPELINE_STATS=1\n'
                       'EDEN_NX2_PIPELINE_STATS_ALL=1\nEDEN_LOG_FILTER=*:Warning\n')
        self.put(self.app + '/env.txt', environment.encode())
        (self.current / 'env.txt').write_text(environment)
        self.put(self.app + '/dev-settings.txt', b'replay=off\n')
        self.remove(self.app + '/compat-input.txt')
        before = self.get(self.data + '/logs/boot-trace.txt', True)
        before = before.splitlines()[0] if before else b''
        with socket.create_connection((self.args.host, 9021), timeout=10) as client:
            client.sendall(self.args.launcher.read_bytes())
            client.shutdown(socket.SHUT_WR)
        deadline = time.monotonic() + 90
        while True:
            data = self.get(self.data + '/logs/boot-trace.txt', True)
            if data and data.splitlines()[0] != before:
                boot = data.splitlines()[0]
                break
            if time.monotonic() > deadline:
                raise RuntimeError('No fresh candidate boot')
            time.sleep(1)
        self.log('Run ' + label + ': ' + boot.decode(errors='replace'))
        start = time.monotonic()
        events = [(55, 'a'), (70, 'a'), (85, 'a'), (190, 'walk'), (200, 'capture')]
        last_collect = -30
        while time.monotonic() - start < self.args.seconds:
            elapsed = time.monotonic() - start
            while events and elapsed >= events[0][0]:
                _, action = events.pop(0)
                if action == 'a':
                    self.pulse()
                elif action == 'walk':
                    self.pulse(mask=0, duration=3000, ly=0)
                else:
                    self.screenshot('scene')
            if elapsed - last_collect >= 30:
                self.collect()
                current_boot = (self.current / 'boot.txt').read_bytes().splitlines()[0]
                if current_boot != boot:
                    raise RuntimeError('Application restarted during the run')
                text = (self.current / 'eden_log.txt').read_text(errors='replace') if (self.current / 'eden_log.txt').exists() else ''
                counts = {backend: len(set(re.findall(r'NX2_COMPILE_TIME hash=(\w+).*' + backend + r'_us=', text))) for backend in ('nir', 'spirv')}
                self.log(f'{label} t={elapsed:.0f}s programs={counts}')
                last_collect = elapsed
            time.sleep(1)
        self.screenshot('end')
        self.stop()
        self.collect()
        boot_text = (self.current / 'boot.txt').read_text(errors='replace')
        heap_text = (self.current / 'heap.log').read_text(errors='replace')
        if 'game loaded (status 0)' not in boot_text:
            raise RuntimeError('The fresh process did not report a successful game load')
        if ('EDEN_ENV EDEN_NX2_NIR=' + str(int(enabled))) not in heap_text or \
           ('EDEN_ENV EDEN_NX2_NIR_EXTENDED_COMPUTE=' + str(int(extended))) not in heap_text:
            raise RuntimeError('Mode environment was not confirmed by the fresh process')
        for path, _ in self.caches:
            if self.exists(path):
                self.remove(path)
        self.remove(self.save)
        self.log('Finished ' + label)

    def restore(self):
        if not self.deployed:
            for path in self.generated:
                if self.exists(path):
                    self.remove(path)
            return
        if not self.exists(self.app + '/eboot.bin'):
            # A failed second rename must not strand an otherwise untouched installation.
            self.rename(self.original_eboot, self.app + '/eboot.bin')
            for path in self.generated:
                if self.exists(path):
                    self.remove(path)
            self.log('Deployment interrupted; original executable restored')
            return
        if digest(self.get(self.app + '/eboot.bin')) != self.candidate_hash:
            raise RuntimeError('Executable changed externally; original backups preserved, refusing overwrite')
        self.stop()
        self.collect()
        for path, backup in self.caches:
            if self.exists(path):
                self.remove(path)
            if backup:
                self.rename(backup, path)
        if self.save:
            if self.exists(self.save):
                self.remove(self.save)
            self.rename(self.save_backup, self.save)
            for local in (self.out / 'private-backup/save').rglob('*'):
                if local.is_file():
                    remote = self.save + '/' + local.relative_to(self.out / 'private-backup/save').as_posix()
                    if self.get(remote) != local.read_bytes():
                        raise RuntimeError('Save restoration mismatch')
        for path, data in self.backups.items():
            if data is None:
                self.remove(path)
            else:
                self.put(path, data)
            if self.get(path, True) != data:
                raise RuntimeError('Settings restoration mismatch')
        self.remove(self.app + '/eboot.bin')
        self.rename(self.original_eboot, self.app + '/eboot.bin')
        if digest(self.get(self.app + '/eboot.bin')) != self.original_hash:
            raise RuntimeError('Executable restoration mismatch')
        self.stop_log.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=3)
        (self.out / 'restored.json').write_text(json.dumps({'executable_verified': True,
            'settings_verified': True, 'save_byte_identical': True, 'caches_restored': True}, indent=2))
        self.log('Original executable, settings, save and caches restored and verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.0.190')
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--modes', nargs='+', choices=('baseline', 'expanded', 'spirv'), default=['baseline', 'expanded', 'spirv'])
    parser.add_argument('--seconds', type=int, default=240)
    args = parser.parse_args()
    if args.runs < 1 or args.seconds < 210:
        parser.error('Need at least one run and 210 seconds to reach the reference scene')
    for path in (args.candidate, args.elf, args.launcher):
        if not path.is_file():
            parser.error('Missing input: ' + str(path))
    if os.environ.get('EGLANTINE_CONSOLE_LEASE_HOST') != args.host:
        lease = Path(__file__).with_name('console-lease.py')
        subprocess.run([sys.executable, str(lease), '--host', args.host, '--owner', 'nir-console-check',
                        'run', '--wait', '--', sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], check=True)
        return
    console = Console(args)
    try:
        console.initialize()
        for repetition in range(1, args.runs + 1):
            for mode in args.modes:
                console.run(mode, repetition)
    finally:
        console.restore()


if __name__ == '__main__':
    main()
