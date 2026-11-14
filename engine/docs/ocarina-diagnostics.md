# Ocarina Reborn diagnostic timeline

On Windows, normal game runs collect bounded diagnostic history. Press **Ctrl+F8**
when a problem occurs. **F1 → Gameplay → Bug report** also marks the timeline.
Afterwards, close the game and use **Create Debug Package** in the launcher.
Describe the room, boss or ocarina song, the steps and approximate time.
The launcher’s **Diagnostic tools** window explains the workflow and offers a
separate, optional 30-second Windows trace.

## What is recorded

- One-second snapshots with actual game frames, worst frame and 50/100 ms counts,
  renderer and delayed GPU timing, pipeline/program creation, translation,
  uploads, memory synchronization, GPU slot waits, texture eviction/readback work.
- Process CPU time across cores and the eight busiest sampled guest threads,
  working set, private commit, available physical RAM, system commit/limit and
  the renderer’s VRAM use/budget with an explicit availability flag.
- Timed native file reads, native zstd decompression, and instrumented guest waits.
  On an incident, currently active phases lasting at least 50 ms are included.
- Last game-provided map, loading/event/age state and the age of that snapshot.
  Context can be stale during loads and unavailable before the first player update.
- Requested and applied audio voice transitions; these are voice IDs, **not song
  IDs**. No sound or wave-buffer contents are recorded.
- In-game settings-save and focus events, user markers, exact EXE/renderer hashes,
  starting/ending settings, mod names/enabled state, launcher and engine versions.

## Limits and interpretation

The recorder holds 30 one-second samples in memory, retains ten seconds after an
incident and saves one sample every five seconds between incidents. Frames over
100 ms trigger a history capture (at most once per 30 seconds for automatic
frame triggers). Markers and no-frame observations extend the capture. A lack of
frames for five seconds, or no first frame after 30 seconds, is an observation;
loading, shader preparation and background windows can explain it. The recorder
does not terminate the game or diagnose a deadlock from that fact alone.

Rendering and file-reading threads do not write the timeline to disk. Their
bounded updates use atomic counters or a try-lock. A low-priority worker writes
the file. Its collection and previous complete iteration times are recorded.
The event queue holds 32 entries per sampling interval; dropped-frame/event
counters make lost evidence visible. Files rotate at 8 MiB; the latest two segments
are retained (16 MiB total per run). Limit/continuation records identify rotation,
so logging continues in long sessions while older evidence is discarded.
Startup/export failures must not prevent playing.
Phase slots cover up to 256 thread lifetimes. Further threads still contribute
aggregate timings but skip phase registration; `untracked_phase_threads` reports
that limit without repeated hot-path scanning. CPU sampling considers up to 128
registered guest threads and reports the busiest eight among them.

Stage durations overlap across parallel workers and nested operations. They are
not an exclusive breakdown of a single frame. Process CPU milliseconds can exceed
wall-clock milliseconds on multiple cores. Native zstd measurements exclude the
lifted decompressor; uninstrumented work is unknown, not zero. GPU timing may
arrive later than the frame that submitted it. Do not infer causation merely from
simultaneous activity. The timeline cannot prove which other application caused
contention; use an optional Windows trace for difficult cases.

History can repeat samples: deduplicate by run ID and `seq`. The paired run JSON
contains the timeline filename and a summary of retained observations, not whole
session FPS. `clock_anchor` aligns its monotonic milliseconds with UTC.
`context_age_ms` distinguishes current from stale room information.

## Crash functions and package contents

The local build exports function names/RVAs from its COFF symbol table to
`ocarina_reborn.exe.symbols.json` and `ocarina_reborn_vk.dll.symbols.json`. These
contain no executable bytes or game assets. The launcher retains up to 20
indexes. Only an index with the exact binary SHA256 is used to resolve a recorded
module-relative stack. The result names the nearest function, not a source line;
stack unwinding may be incomplete. Retain the linker maps when developing.

The ZIP includes the performance and comparison reports, native crash reports,
resolved stacks, matching retained function indexes, bounded text logs and
timelines, settings, issue description and a manifest of omissions/truncation.
It includes no saves, keys, executables, audio, game resources, raw memory dumps
or ETL traces. Known home/game/app directory prefixes are replaced. Text files
are limited to 8 MiB each (function indexes: 16 MiB) with a 64 MiB input budget. Structured reports that
exceed the budget are omitted explicitly instead of being cut into invalid JSON.
Twenty run records are retained locally; direct EXE launches retain the latest
standalone timeline in the game folder.

## Optional Windows trace

WPR uses `GeneralProfile.Light` in bounded memory mode for 30 seconds after a
five-second countdown. The user must explicitly start it and Windows may require
an elevated launcher. Every operation names a unique `OcarinaReborn-...` WPR
instance; another recording is never stopped or cancelled. ETL files may contain
system-wide activity and paths, are stored separately under Reports, and require
a separate sharing decision. No automatic upload is performed.

## Development

`OCR_DIAGNOSTICS=0` disables the native recorder for controlled A/B checks.
`OCR_TRACE_FILE` chooses its output; the launcher sets it uniquely per run.
Renderer/host ABI version 22 adds the diagnostic callbacks: update both components.
This uses the existing compiled game code; importing/extracting the game again is
not required. Native unit tests use authored samples and a synthetic executable;
do not publish private game builds used for integration tests.
