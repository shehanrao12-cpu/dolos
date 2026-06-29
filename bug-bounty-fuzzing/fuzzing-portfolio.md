# OSS Fuzzing Portfolio — Targets, Fuzzers, and How to Run Them

A practical, rotating portfolio for fuzzing open-source software that (a) is likely
to contain memory-safety bugs and (b) has a program that is likely to pay. The
guiding idea: run several **big-corp fuzzers** across several targets in parallel,
keep whatever produces, and swap out anything that goes quiet or stops paying.

> **Why only big-corp fuzzers?** Because the *report* is the product. libFuzzer,
> AFL++, Honggfuzz, Atheris, and Go's native fuzzer are all wired to **sanitizers**
> (ASan/MSan/UBSan). When they crash, the output *classifies the bug for you* —
> bug class, READ vs WRITE, allocation/free/crash stack traces — so you can tell a
> genuine, payable memory-corruption from harmless noise (a leak, an OOM, a
> timeout) in seconds. See "Reading the report" below.

---

## 1. The roster

### C / C++ — memory-safety targets (primary)

| # | Project | What it parses | Fuzzer + Sanitizer | Aim the harness at | Pays via |
|---|---|---|---|---|---|
| 1 | **systemd** | unit files, journal, DNS/DHCP | libFuzzer + ASan/UBSan | DNS/DHCP packet parsing, journal reader | Sovereign Tech (€500–10k) |
| 2 | **GNOME libsoup** | HTTP requests/headers | libFuzzer + ASan | header & chunked-body parsing | Sovereign Tech |
| 3 | **GNOME GLib** | GVariant, URIs, data structures | libFuzzer + ASan/UBSan | GVariant deserialization, URI parser | Sovereign Tech |
| 4 | **libcurl** | many network protocols | AFL++ + libFuzzer | URL parser, rarer protocols (TFTP, IMAP) | curl bounty (HackerOne) |
| 5 | **Exiv2** | image metadata (EXIF/XMP/IPTC) | libFuzzer + ASan | **encoder/write path** (still produced 2025 CVEs) | project / OSS-VRP-class |
| 6 | **libtiff** | TIFF images | AFL++ + ASan | TIFF *writer*, exotic tags | project |
| 7 | **OpenEXR** | HDR images | libFuzzer + ASan | deep/tiled formats, compression codecs | project |
| 8 | **LibRaw** | camera RAW formats | AFL++ + ASan | per-vendor RAW decoders (under-fuzzed) | project |
| 9 | **FreeType** | fonts | libFuzzer + ASan | CFF/TrueType hinting paths | project / OSS-VRP-class |
| 10 | **HarfBuzz** | text shaping | libFuzzer + ASan | shaping for complex scripts | project |
| 11 | **libarchive** | tar/zip/7z/cpio… | AFL++ + ASan | rarer formats (LHA, XAR, WARC) | project |
| 12 | **libxml2 / expat** | XML | libFuzzer + ASan | DTD/entity handling, push parser | project |
| 13 | **c-ares** | async DNS | libFuzzer + ASan | DNS response parsing | project (used everywhere) |

### Other languages (logic bugs, different payers)

| # | Project | Fuzzer | Aim at | Pays via |
|---|---|---|---|---|
| 14 | **Pillow** (Python, C core) | Atheris | image plugin decoders | project / huntr |
| 15 | **Go protobuf / Go stdlib parsers** | `go test -fuzz` | proto unmarshal, `encoding/*` | Google OSS VRP ($100–31,337) |

**Choosing the fuzzer per target**
- **libFuzzer** — project exposes a clean in-process function to call (most parsers). Native OSS-Fuzz engine → harness reusable for integration rewards.
- **AFL++** — input is a *file* fed to a CLI/tool, or no easy in-process entry point.
- **Atheris** — Python and Python C-extensions.
- **`go test -fuzz`** — Go libraries.
- **Sanitizer**: always **ASan**; add **UBSan** for C (integer/overflow UB); **MSan** only if every dependency is also built with it.

---

## 2. How to get them fuzzing

### libFuzzer (the default for C/C++ libraries)

A harness is a single function. Minimal example for an image/metadata lib:

```c
// harness.c — fuzz an in-process parser entry point
#include <stdint.h>
#include <stddef.h>
extern int parse_buffer(const uint8_t *data, size_t size); // the target API

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    parse_buffer(data, size);
    return 0;
}
```

Build with Clang, ASan + UBSan + coverage, then run:

```bash
clang -g -O1 -fsanitize=fuzzer,address,undefined \
    harness.c target_lib.a -I target/include -o fuzz_target

mkdir corpus
./fuzz_target corpus/ -max_len=65536 -jobs=$(nproc)   # parallel across cores
```

- `-jobs=$(nproc)` launches one worker per core (built-in parallelism).
- Seed `corpus/` with real sample files (valid TIFFs, fonts, etc.) for faster coverage.
- A crash drops a `crash-<hash>` reproducer file in the cwd.

### AFL++ (for CLI tools / file inputs)

```bash
# build the target with AFL++'s instrumenting compiler
CC=afl-clang-fast CXX=afl-clang-fast++ ./configure && make

mkdir in out && cp sample_inputs/* in/
# parallel: one master (-M) + several secondaries (-S), one per core
afl-fuzz -i in -o out -M main -- ./target @@ &
afl-fuzz -i in -o out -S sec1 -- ./target @@ &
afl-fuzz -i in -o out -S sec2 -- ./target @@ &
```

`@@` is replaced with the input file path. Build with `AFL_USE_ASAN=1` to get
sanitizer-quality crash reports.

### Atheris (Python)

```bash
pip install atheris
```
```python
import atheris, sys
with atheris.instrument_imports():
    from PIL import Image
    import io

def TestOneInput(data):
    try:
        Image.open(io.BytesIO(data)).load()
    except Exception:
        pass  # only crashes / memory errors matter

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
```

### Go native fuzzing

```go
func FuzzUnmarshal(f *testing.F) {
    f.Fuzz(func(t *testing.T, data []byte) {
        var m pb.Message
        proto.Unmarshal(data, &m)
    })
}
```
```bash
go test -fuzz=FuzzUnmarshal -fuzztime=1h
```

### ClusterFuzzLite — free parallel/continuous fuzzing in GitHub Actions

Fork the target, add `.github/workflows/cflite_batch.yml` for scheduled batch
fuzzing — Google's ClusterFuzz engine runs your harnesses in CI for free (within
GitHub Actions quota). Good for keeping several targets grinding 24/7 without your
own hardware. Use **batch mode** on a schedule (not first-crash PR mode) for hunting.

---

## 3. Reading the report — is it genuine and payable?

This is why the sanitizer-backed fuzzers are worth it. A typical ASan crash:

```
==1234==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x...
READ of size 4 at 0x... thread T0
    #0 parse_tag  target/tiff.c:812
    #1 read_ifd   target/tiff.c:640
    #2 TIFFReadDirectory ...
0x... is located 0 bytes to the right of 16-byte region allocated here:
    #0 malloc
    #1 alloc_entries target/tiff.c:600
```

How to judge it:

| Signal in the report | Meaning | Payable? |
|---|---|---|
| `heap-buffer-overflow`, `stack-buffer-overflow`, `use-after-free`, `global-buffer-overflow` | Real memory corruption | ✅ Usually yes |
| `WRITE of size N` | Out-of-bounds **write** — corrupts memory | ✅✅ Highest value (often RCE-grade) |
| `READ of size N` | Out-of-bounds read — info leak / crash | ✅ Yes, lower than WRITE |
| `use-after-free` with alloc + free + use traces | Classic exploitable bug | ✅✅ High value |
| `memory leak`, `out-of-memory`, `timeout` | Resource issue, not corruption | ⚠️ Usually **not** a security bug — low/no pay |
| `assertion failed` / clean `NULL deref` | Often just a robustness bug | ⚠️ Frequently out of scope |

Then, before reporting:
1. **Reproduce** with the saved crash file (`./fuzz_target crash-<hash>`).
2. **Minimize** it (libFuzzer: `-minimize_crash=1`; AFL++: `afl-tmin`).
3. **Confirm reachability** — is this input something an attacker actually controls
   (a file/packet a real app would process)? An unreachable crash gets rejected.
4. **State the impact** in the report: bug class, WRITE vs READ, what an attacker
   achieves. Attach the minimized reproducer + sanitizer trace.

The sanitizer trace *is* most of a good report — it shows the maintainer the exact
bug class and location, which is what makes a report credible and fast to triage.

---

## 4. The operating loop

1. **Seed**: pick 4–6 targets from §1; for each write **one new harness** aimed at the
   under-covered path in column "Aim the harness at" (encoders, rarer formats,
   push/streaming parsers — that's where bugs survived years of fuzzing).
2. **Run parallel**: local cores (`-jobs=$(nproc)` / AFL++ `-M`/`-S`) + ClusterFuzzLite in CI.
3. **Triage** each crash with §3.
4. **Report** to the project's program; if the project isn't on OSS-Fuzz, also pursue
   the **OSS-Fuzz integration reward** (up to ~$30k) for the harness itself.
5. **Rotate**: target goes quiet or stops paying → drop it, pull the next from the backlog.

---

## 5. Payer reality (2026)

- **Internet Bug Bounty (IBB)** — **PAUSED** new submissions (Mar 27 2026) and slashed
  payouts. Was the main core-OSS payer; not a plan right now. Watch for its return.
- **Sovereign Tech Fund / Agency (YesWeHack)** — active, €500–€10,000. Covers systemd,
  GNOME (GLib/libsoup), and others; explicitly invites memory-safety reports.
- **Google OSS VRP** — active, $100–$31,337; covers Google's OSS (Go, protobuf, Bazel,
  Angular, Fuchsia). Paid ~$327k across 62 rewards in 2025.
- **Project-specific bounties** — e.g., curl (HackerOne). Check each project's
  `SECURITY.md` for scope and authorization before testing.
- **OSS-Fuzz integration rewards** — up to ~$30k for newly integrating a project
  (separate from any bug bounty). Pays you for the harness, not the bug.

> Many excellent fuzz targets have **no cash bounty** — for those the payoff is CVE
> credit + the OSS-Fuzz integration reward, not a bounty. Always confirm a program
> exists and you're in scope before reporting.

---

## 6. Worked example, end to end (exact commands)

Two concrete walkthroughs: one that is trivially runnable (Exiv2), and one that
maps to a **cash** program (libsoup → Sovereign Tech).

### 6a. Exiv2 — runnable today (CVE credit; encoder path still yields 2025 bugs)

```bash
# 1. Get the source
git clone https://github.com/Exiv2/exiv2
cd exiv2

# 2. Build with Clang + libFuzzer + ASan + UBSan, fuzz targets enabled
cmake -B build \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_CXX_FLAGS="-g -O1 -fsanitize=fuzzer-no-link,address,undefined" \
  -DEXIV2_BUILD_FUZZ_TESTS=ON -DEXIV2_ENABLE_PNG=ON -DEXIV2_ENABLE_WEBP=ON
cmake --build build -j"$(nproc)"

# 3. Seed a corpus with real sample images (better coverage, faster bugs)
mkdir corpus
cp test/data/*.jpg test/data/*.tif test/data/*.png corpus/ 2>/dev/null

# 4. Run the fuzzer in parallel across all cores
./build/bin/fuzz-read-print-write corpus \
  -jobs="$(nproc)" -workers="$(nproc)" -max_len=1000000
```

When it crashes it writes a `crash-<hash>` file and prints an ASan report. Triage
with §3, minimize, then report via Exiv2's GitHub "Report a vulnerability"
(private security advisory). Exiv2 gives **CVE credit**, not cash — use it to build
a track record, then point the *same technique* at a paying target below.

### 6b. libsoup — the cash version (Sovereign Tech via YesWeHack, €500–10k)

```bash
# 1. Source
git clone https://gitlab.gnome.org/GNOME/libsoup
cd libsoup

# 2. Build with Meson, Clang, sanitizers, fuzzers on
CC=clang CXX=clang++ meson setup build \
  -Dfuzzing=enabled -Db_sanitize=address,undefined -Dbuildtype=debugoptimized
meson compile -C build

# 3. The harnesses live in fuzzing/ ; run the HTTP header/message parser one
mkdir corpus
./build/fuzzing/<harness-binary> corpus -jobs="$(nproc)" -max_len=65536
```

> Always check each repo's `fuzzing/`, `fuzz/`, or `oss-fuzz/` directory and its
> build docs — option names (`-Dfuzzing`, `EXIV2_BUILD_FUZZ_TESTS`, etc.) differ
> per project. The *pattern* is identical everywhere: build with
> `clang -fsanitize=fuzzer,address,undefined`, seed a corpus, run with
> `-jobs=$(nproc)`.

### Writing your OWN harness (the edge — under-fuzzed paths)

If the target only fuzzes the decoder, write a target for the **encoder/writer**:

```cpp
// fuzz_write.cc — libFuzzer harness for an under-fuzzed write path
#include <cstdint>
#include <cstddef>
extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    // 1. read attacker-controlled input into the library's object model
    // 2. then call the WRITE/ENCODE path that existing harnesses skip
    //    e.g. parse metadata -> modify -> serialize back out
    return 0;
}
```
```bash
clang++ -g -O1 -fsanitize=fuzzer,address,undefined \
  fuzz_write.cc -I target/include target/lib.a -o fuzz_write
./fuzz_write corpus -jobs="$(nproc)"
```

---

## 7. Exact steps to claim the bounty

Once §3 says the crash is a genuine, reachable memory-corruption:

1. **Minimize the reproducer**
   - libFuzzer: `./fuzz_target -minimize_crash=1 -runs=100000 crash-<hash>`
   - AFL++: `afl-tmin -i crash-file -o min-file -- ./target @@`
2. **Re-confirm** it still crashes on a clean build and capture the **full ASan trace**.
3. **Write the report** containing exactly:
   - Bug class + READ/WRITE (from the sanitizer header line)
   - The minimized input file (attach it) + the crashing stack trace
   - **Reachability/impact**: name a real entry point an attacker controls (a file a
     user opens, a packet a server receives) and what the bug achieves
     (RCE-grade write, info leak, etc.)
   - Affected version / commit, and build flags used
4. **Submit through the program that owns the project** (do *not* post it publicly first):

   | Project | Where to submit | Reward |
   |---|---|---|
   | systemd, GLib, libsoup, and other Sovereign Tech scopes | YesWeHack program page for that project | €500–€10,000 |
   | Google OSS (Go, protobuf, Bazel, Angular, Fuchsia) | https://bughunters.google.com → OSS VRP | $100–$31,337 |
   | curl / libcurl | https://hackerone.com/curl | varies |
   | Project with only a `SECURITY.md` (no cash) | GitHub "Report a vulnerability" / security email | CVE credit |
   | Project you newly added fuzzing to | OSS-Fuzz integration reward (separate) | up to ~$30k |

5. **Coordinated disclosure**: keep it private until the maintainer ships a fix and
   agrees to disclose. Premature public disclosure can void the reward.
6. **For the OSS-Fuzz integration reward**: upstream your harness into the project's
   repo, get it building under OSS-Fuzz with sanitizers and >80% coverage, then claim
   per https://google.github.io/oss-fuzz/getting-started/integration-rewards/

**Realistic note:** "big bounty" here means low-thousands (Sovereign Tech) up to
$31,337 (Google OSS VRP) for a strong report — not lottery money, and only for a
*genuine, reachable, high-impact* bug with a clean reproducer. A raw crash with no
demonstrated security impact is typically rejected. The portfolio pays through
*volume of valid reports over time*, not a single hit.

---

## Sources

- Internet Bug Bounty — https://hackerone.com/ibb
- HackerOne reward cuts (The Register) — https://www.theregister.com/security/2026/05/21/hackerone-takes-an-axe-to-its-bug-bounty-rewards/
- Google OSS VRP rules — https://bughunters.google.com/about/rules/open-source/google-open-source-software-vulnerability-reward-program-rules
- Google VRPs in Review 2025 — https://bughunters.google.com/blog/google-vrps-in-review-2025
- OSS-Fuzz integration rewards — https://google.github.io/oss-fuzz/getting-started/integration-rewards/
- OSS-Fuzz new project guide — https://google.github.io/oss-fuzz/getting-started/new-project-guide/
- ClusterFuzzLite (GitHub Actions) — https://google.github.io/clusterfuzzlite/running-clusterfuzzlite/github-actions/
- Bugs that survive continuous fuzzing (GitHub Blog) — https://github.blog/security/vulnerability-research/bugs-that-survive-the-heat-of-continuous-fuzzing/
- Sovereign Tech Fund bug bounty (YesWeHack) — https://www.yeswehack.com/community/open-source-sovereign-tech-fund
- libFuzzer docs — https://llvm.org/docs/LibFuzzer.html
