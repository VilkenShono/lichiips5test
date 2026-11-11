# LichiiPS5 port — working notes (keep updated)

## Facts
- PS5 port repo: /home/claude/heydemoura/eglantineps5 (heydemoura/EglantinePS5 @ 268d43a, shallow)
  - core = submodule `Eglantine` -> zortos293/Eglantine @ 3140648a (the "pin"), + 74 patches in tools/eglantine-patches
  - build-time text rewrites: tools/prepare-vulkan-port.py (196 anchors), headless/CMakeLists.txt (+ *.cmake), ~80 tools/check-*.py gates
- Lichii: /home/claude/zortos293/lichii (zortos293/Lichii nx2 @ 4e7d87a, history fetched depth 2500)
  - pin 3140648a IS an ancestor, but de6efea6d (2 Nov) re-based the tree ("refreshed game-fix tree"): many pin files deleted
  - branches: ps5-at-pin = pin + 74 patches (as commits); ps5-merge = scratch at lichii head
- Worktrees: /home/claude/work/core-pin (pin+patches), /home/claude/work/core-lichii (plain Lichii head)
- Naive merge of ps5-at-pin into Lichii head: 132 conflicted files / 528 hunks -> NOT the route.
- Strategy: "Lichii wins". Start from unpatched Lichii head; re-add PS5 core patches only where the port needs them.
- Network: only github.com git reads work here. No PS5 SDK archives, no pip/apt. No PS5 build possible locally.
- Repo has GitHub Actions release build (.github/workflows/release.yml, workflow_dispatch). User has no repos connected yet.

## Tools (scratchpad = /tmp/claude-0/-home-claude/c95c903f-781f-5ce4-b0b1-1945b9374d7f/scratchpad)
- stubbin/ : fake glslangValidator, spirv-val (for anchor checks)
- anchor_report.py <prepare-vulkan-port.py> <core> <out> [--list] : per-anchor report
- upstream_score.py, replay.sh : patch analysis

## Status log
- [done] analysis of divergence

## Update 15:35 (11 Nov)
- zortos293/Eglantine == zortos293/Lichii (renamed; ls-remote HEAD = 4e7d87a). Submodule URL already valid.
- User repo: VilkenShono/lichiips5test (public, push OK incl. workflows). Clone: /home/claude/lichiips5test
  - main = 39690fc (upstream snapshot, orphan) + 872c1cb (.github/workflows/port-ci.yml)
  - port-ci.yml: builds on push to ci/* ; logs -> branch `ci-logs` (status.txt, *.errors.txt, *.log); ZIP artifact
  - pushed ci/baseline (unmodified upstream) at 15:33 to validate the pipeline. Check: git -C /home/claude/lichiips5test fetch origin ci-logs
  - gh CLI is NOT authenticated; only git works. Identity for commits: Claude <noreply@anthropic.com> (never the user's email)
- Port work tree: /home/claude/work/port (branch lichii-port of local eglantineps5 clone); core tree: /home/claude/work/core (branch ps5-core, Lichii head)
- Harness: tools/run_harness.sh <port> <core> <name> [-DHARNESS_FORCE=ON -DHARNESS_OPTIONAL=...]; baseline misses in out-pin/harness.log
  - CMake rules on plain Lichii: ~67 new misses (26 in multiplayer_packets.cmake), see out-lichii0/new-misses.log
- Vulkan script: tools/vk_report.sh <port> <core> <name>; show.py / locate.py on vk-<name>/anchors.json: 61 broken + 17 custom steps
- Decision: "Lichii wins": no blanket patch rebase. Core patches carried only when needed. Drop diag/perf rewrites that no longer anchor.
