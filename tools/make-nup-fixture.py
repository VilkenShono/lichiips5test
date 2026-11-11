#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Makes the containers headless/nup_check.cpp reads (fixtures/nup/).

The dump it packs is made up: an NPDM (Switch 2 ACID layout), a stand-in main, a RomFS with a
file only the base has, one the update replaces and one of 9 MiB (above the size the reader
decompresses into memory), an update and a DLC. It is packed by the reference tool of the format,
https://github.com/a55uka/nup (tools/nup, `pip install ./tools/nup`):

    python3 tools/make-nup-fixture.py --nup <path to the nup command> [--out fixtures/nup/sample.nup]

sample.nup is packed by the tool as of a4840f0, which numbers the meta types from 0 (NPDM 0, as
since its 1d904e1); sample-spec-meta.nup by the tool as of a34925a, which numbers them as
SPEC.md does (NPDM 1). The reader takes both.
"""
import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile

TITLE_ID = 0x0400ABCD12340000
DLC_ID = 0x0400ABCD12341001
UPDATE_VERSION = 65536  # 1.0.0 -> update 0x10000


def npdm(title_id: int) -> bytes:
    """A META with a Switch 2 ACID (0x300-byte signature area) and an ACI0."""
    acid_offset, acid_size = 0x80, 0x400
    aci_offset, aci_size = 0x480, 0x100
    data = bytearray(aci_offset + aci_size)
    header = bytearray(0x80)
    header[0:4] = b"META"
    header[0x0C] = 0x01 | (2 << 1)  # 64-bit, 39-bit address space
    header[0x0E] = 44  # main thread priority
    header[0x0F] = 0  # main thread core
    struct.pack_into("<I", header, 0x1C, 0x100000)  # main stack size
    header[0x20:0x20 + 9] = b"nupsample"
    struct.pack_into("<IIII", header, 0x70, aci_offset, aci_size, acid_offset, acid_size)
    data[0:0x80] = header
    acid = acid_offset + 0x300  # body after the Switch 2 signature area
    data[acid:acid + 4] = b"ACID"
    struct.pack_into("<I", data, acid + 4, acid_size)
    struct.pack_into("<I", data, acid + 0x0C, 1 << 2)  # application pool partition
    struct.pack_into("<QQ", data, acid + 0x10, title_id, title_id)
    # FAC/SAC/KAC offsets are relative to the ACID block; empty but in bounds.
    struct.pack_into("<IIIIII", data, acid + 0x20, 0x340, 0x2C, 0x370, 0, 0x370, 0)
    struct.pack_into("<B", data, acid_offset + 0x340, 1)  # FAC version
    aci = aci_offset
    data[aci:aci + 4] = b"ACI0"
    struct.pack_into("<Q", data, aci + 0x10, title_id)
    struct.pack_into("<IIIIII", data, aci + 0x20, 0x40, 0x1C, 0x60, 0, 0x60, 0)
    struct.pack_into("<B", data, aci + 0x40, 1)  # FAH version
    return bytes(data)


def main_nso(tag: bytes) -> bytes:
    """Not a runnable NSO: enough for the build ID (bytes 0x40..0x60) and for telling base from update."""
    data = bytearray(0x100)
    data[0:4] = b"NSO0"
    data[0x40:0x60] = (tag * 32)[:32]
    return bytes(data)


def write(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nup", required=True, help="the reference tool's nup command")
    parser.add_argument("--out", default=str(pathlib.Path(__file__).resolve().parent.parent / "fixtures/nup/sample.nup"))
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    with tempfile.TemporaryDirectory() as work:
        dump = pathlib.Path(work) / "dump"
        base = dump / "base"
        write(base / "exefs/main", main_nso(b"B"))
        write(base / "exefs/main.npdm", npdm(TITLE_ID))
        write(base / "romfs/base_only.txt", b"from the base\n")
        write(base / "romfs/data/shared.txt", b"base version\n")
        write(base / "romfs/data/big.bin", bytes(i % 251 for i in range(9 << 20)))
        update = dump / "updates" / str(UPDATE_VERSION)
        write(update / "exefs/main", main_nso(b"U"))
        write(update / "exefs/main.npdm", npdm(TITLE_ID))
        write(update / "romfs/data/shared.txt", b"update version\n")
        write(dump / "dlc" / f"{DLC_ID:016x}" / "0" / "romfs/dlc.txt", b"dlc\n")
        # A 1x1 JPEG: the icon a library shows.
        icon = pathlib.Path(work) / "icon.jpg"
        icon.write_bytes(bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f0000010501010101010100000000000000000102030405060708090a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9faffda0008010100003f00fbd3ffd9"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.unlink(missing_ok=True)
        subprocess.run([args.nup, "pack", str(dump), str(out), "--name", "NUP Sample", "--display-version", "1.0.1",
                        "--publisher", "EglantinePS5 checks", "--icon", str(icon), "-q"], check=True)
        subprocess.run([args.nup, "verify", str(out)], check=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
