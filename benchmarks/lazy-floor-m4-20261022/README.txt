Lazy useful-match floor: Apple M4 Max measurements (2026-10-22)
Baseline: 49cf51799ea051457f57243527aa2058f999f005
Patch: c0002-r0; code commit 09fd6a001bdb5e30128329334dd4980d5195365c
Apple M4 Max / macOS 26.3 / Apple Clang 17 / -O3 / single thread / no dictionary.
Data: full 12-file Silesia corpus, 211938580 bytes, concatenated alphabetically; not silesia.tar.

Consolidated compression (separate median speeds; change is median of paired ratios):
Level   Baseline MB/s   Candidate MB/s    Paired change    Compressed bytes / ratio
1             548.65           548.51          -0.031%     73213479 / 2.895
3             320.50           320.48          +0.050%     66121941 / 3.205
6             125.12           125.76          +0.551%     61230924 / 3.461
9              83.75            86.70          +3.645%     59073803 / 3.588
Each consolidated comparison uses seven rounds at -i2. Corresponding CLI A/A compression pair changes ranged from -0.285% to +0.257%.

Per-file median paired compression changes (%), five alternating pairs, -i1:
File           L6        L9
dickens         -0.522%    +3.248%
mozilla         +1.303%    +3.126%
mr              -0.328%    +0.354%
nci             -0.087%    +1.863%
ooffice         +0.590%    +1.167%
osdb            -0.841%    +2.186%
reymont         +3.160%    +7.553%
samba           +1.807%    +5.513%
sao             -0.950%    -0.101%
webster         +1.070%    +5.370%
x-ray           -1.130%    -0.359%
xml             +3.060%    +8.467%
Equal-weight geometric mean of per-file paired medians: L6 +0.584%; L9 +3.161%. Level-6 results include regressions down to -1.130%; these small individual losses were not separately extended to long-duration runs. L9 file medians improve in 10/12 cases.
Decompression measurements are retained in summary.json/CSV; small shifts for this compression-only source patch should not be interpreted as a decoder algorithm improvement.

Correctness: make check passes in baseline and candidate. Concatenated-corpus output is byte-identical and round-trips at L1/3/6/9. Per-file benchmark sizes are unchanged. Separate -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined DEBUGLEVEL=1 tests/fuzzer -T60s -s22 and tests/zstreamtest -T30s -s22 pass. These are bounded checks, not the complete upstream CI suite.
Limits: one Mac/compiler/data family; default strategies only. CPU affinity/frequency/turbo/ASLR were not controlled and normal desktop apps remained. No code-alignment perturbation runs or dictionary/streaming timing claims. Interval estimates in summary.json are descriptive small-sample bootstrap intervals, not multiplicity-adjusted acceptance guarantees.

Reproduce:
  git clone https://github.com/facebook/zstd.git upstream-zstd
  curl -L --fail https://sun.aei.polsl.pl/~sdeor/corpus/silesia.zip -o silesia.zip
  shasum -a 256 silesia.zip
  # Expected archive SHA-256: 0626e25f45c0ffb5dc801f13b7c82a3b75743ba07e3a71835a41e3d9f63c77af
  unzip silesia.zip -d silesia
  caffeinate -i python3 reproduce.py --source upstream-zstd --corpus silesia --out fresh-results
Use an otherwise quiet Mac, AC power, and a new output directory. The script verifies every corpus file hash and the patch, archives the pinned source, builds isolated baseline/candidate CLIs, checks compressed bytes/round trips and measures with interleaved process runs. The recheck uses two-binary AB/BA order; the saved original aggregate matrix included a third candidate. Timing results are not expected to match byte-for-byte. For small effects, extend --seconds and --rounds; those arguments affect the consolidated tests, while --per-file-seconds and --per-file-pairs control the file matrix.
The original single-patch code branch contains only lib/compress/zstd_lazy.c; this evidence directory is on a separate branch. No corpus data or binaries are redistributed. $RUN in saved commands/logs replaces the original private local run path.
Files: metadata.json, corpus-files.json, c0002-r0.patch, cli-samples.jsonl, summary.json/CSV, correctness.json, additional-checks.json, test logs, prior-work.json, reproduce.py and SHA256SUMS.
AI assistance: an AI-assisted optimization pipeline produced the candidate. Codex assisted with validation harnesses, benchmarking, analysis and upstream preparation.
