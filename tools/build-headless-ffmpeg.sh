#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
scratch=$(cat "$root/.local/headless-cache")
[[ "$(cat "$scratch/owner")" == "$root" ]]
export PS5_PAYLOAD_SDK="$scratch/sdk"
source="$scratch/source/.cache/cpm/ffmpeg/c7b5f1537d"
test -f "$source/configure"

# dav1d (tools/deps.json) for FFmpeg's libdav1d decoder: Switch 2 titles play AV1 movies, and
# FFmpeg's own av1 decoder only drives hardware decoders. Static, no tools, the same compiler.
dav1d_source="$root/.deps/dav1d-1.5.1"
dav1d="$scratch/dav1d-native"
test -f "$dav1d_source/meson.build"
rm -rf "$dav1d"
mkdir -p "$dav1d"
cat > "$dav1d/cross.txt" <<EOF
[binaries]
c = ['bash', '$root/tools/ffmpeg-ps5-cc.sh']
ar = 'llvm-ar-18'
strip = 'llvm-strip-18'
nasm = 'nasm'
[host_machine]
system = 'freebsd'
cpu_family = 'x86_64'
cpu = 'x86_64'
endian = 'little'
EOF
meson setup "$dav1d/build" "$dav1d_source" --cross-file "$dav1d/cross.txt" --prefix "$dav1d/install" \
    --libdir lib --buildtype release --default-library static -Denable_tools=false \
    -Denable_tests=false -Denable_examples=false -Dlogging=false
ninja -C "$dav1d/build" install

mkdir -p "$scratch/ffmpeg-native"
cd "$scratch/ffmpeg-native"
# Use the same pinned, minimal decoder set as the Linux core, plus AV1 through dav1d. Avoid the
# full prebuilt FFmpeg package's unrelated codec and C++ runtime dependencies.
# meson puts dav1d.pc in libdata/pkgconfig for a freebsd target or in lib/pkgconfig (depends on
# the meson version): look in both.
PKG_CONFIG_LIBDIR="$dav1d/install/libdata/pkgconfig:$dav1d/install/lib/pkgconfig" PKG_CONFIG_PATH= \
bash "$source/configure" --prefix="$scratch/ffmpeg-native/install" \
    --enable-cross-compile --arch=x86_64 --target-os=freebsd \
    --cc="bash $root/tools/ffmpeg-ps5-cc.sh" --ld="bash $root/tools/ffmpeg-ps5-cc.sh" \
    --ar=llvm-ar-18 --ranlib=llvm-ranlib-18 --nm=llvm-nm-18 \
    --pkg-config=pkg-config --pkg-config-flags=--static \
    --disable-autodetect --disable-everything --disable-programs --disable-doc \
    --disable-avdevice --disable-avformat --disable-network --disable-swresample \
    --enable-libdav1d --enable-decoder=h264,vp8,vp9,libdav1d --enable-filter=yadif,scale --enable-pic \
    --enable-pthreads --disable-shared --enable-static
make -j"${EDEN_BUILD_JOBS:-$(nproc)}"
# The AV1 decoder must be in: without it, AV1 movies have no decoder at all.
grep -q "^#define CONFIG_LIBDAV1D_DECODER 1" config_components.h config.h 2>/dev/null
make install
# The app links FFmpeg's libraries by path (FindFFmpeg), without their private dependencies: put
# dav1d's objects in libavcodec.a. An MRI script keeps members with the same name (dav1d builds its
# 8- and 16-bit templates from the same sources), which extracting with `ar x` would overwrite.
avcodec="$scratch/ffmpeg-native/install/lib/libavcodec.a"
printf 'CREATE %s\nADDLIB %s\nADDLIB %s\nSAVE\nEND\n' "$avcodec.merged" "$avcodec" \
    "$dav1d/install/lib/libdav1d.a" | llvm-ar-18 -M
mv "$avcodec.merged" "$avcodec"
llvm-ranlib-18 "$avcodec"
touch "$scratch/ffmpeg-native/install/.with-dav1d"
