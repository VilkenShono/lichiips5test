#!/usr/bin/env bash
# vk_report.sh <port repo> <core tree> <name>: anchor report of tools/prepare-vulkan-port.py
S=/tmp/claude-0/-home-claude/c95c903f-781f-5ce4-b0b1-1945b9374d7f/scratchpad
out=/home/claude/work/vk-$3; rm -rf "$out"; mkdir -p "$out"
cd "$1" && PATH=$S/stubbin:$PATH python3 -I /home/claude/work/tools/anchor_report.py tools/prepare-vulkan-port.py "$2" "$out" > "$out/report.txt" 2>&1
grep -E '^(anchors|other)' "$out/report.txt"; sed -n '/^other failing/,/^broken by file/p' "$out/report.txt" | grep -v NameError | cut -c1-160
