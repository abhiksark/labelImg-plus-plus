# Video workspace supplied-file acceptance — 2026-08-24

## Result

The supported video workspace passed the supplied-file acceptance slice on all
three unique source videos. Each original was opened and decoded first. All
annotation mutations were then made against a per-file copy in
`/private/tmp/labelimgpp-video-acceptance.XXqwsN/`; the source MP4 bytes were
not changed. The copies and their SQLite projects were retained after the run.

The run exercised full-frame fit, frame stepping, playback, three seek paths,
exact-time validation, choose-once/draw-twice annotation, continuous save,
verification, project reopen, propagation cancellation and review, responsive
use, and a real 30-cycle OS-level soak (10 cycles per unique video). All app
processes ended with status 0. No macOS “Python quit unexpectedly” dialog, new
crash report, abandoned-worker warning, or shutdown timeout appeared.

## Environment and optional runtime

- macOS 26.5.2 (25F84), Apple desktop session
- Python 3.9.21
- labelimgplusplus 4.0.0rc0, editable from this worktree
- PyAV 15.1.0, NumPy 2.0.2, OpenCV 5.0.0, PyQt 5.15.11, Qt 5.15.14
- Install command: `python -m pip install -e '.[video]'`
- Install result: success from the package registries already configured for
  the environment; no dependency manifest was changed and video remains an
  optional extra.

The previously skipped PyAV path became active after installation. Importing
PyAV and OpenCV in the same macOS process consistently printed these two
loader warnings:

```text
Class AVFFrameReceiver is implemented in both .../av/.dylibs/libavdevice.61.3.100.dylib and .../cv2/.dylibs/libavdevice.61.3.100.dylib. This may cause spurious casting failures and mysterious crashes. One of the duplicates must be removed or renamed.
Class AVFAudioReceiver is implemented in both .../av/.dylibs/libavdevice.61.3.100.dylib and .../cv2/.dylibs/libavdevice.61.3.100.dylib. This may cause spurious casting failures and mysterious crashes. One of the duplicates must be removed or renamed.
```

This is a residual packaging/runtime warning, not an observed crash: every
acceptance launch and clean quit returned status 0.

## Supplied sources

Duplicate paths from the request were not counted twice.

| ID | Original path | Bytes | SHA-256 | Video metadata |
| --- | --- | ---: | --- | --- |
| V1 | `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-49-10_w.mp4` | 10,351,896 | `04e6148c003d7e29a8dd7900af988855eb9e50d46bbe3424c37d6e0f756941a5` | H.264, 1920×1080, 288 frames, time base 1/90000, average rate 5184000/172789, container duration 9.599389 s |
| V2 | `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-06-31_w.mp4` | 14,272,282 | `2147612e79463a6d61949cb2ac80dfa11c046b2eb52ff85060b4ee83dc781eee` | H.264, 1920×1080, 288 frames, time base 1/90000, average rate 160000/5333, container duration 9.599400 s |
| V3 | `/Users/abhiksarkar/Downloads/Videos/000414_000558_2025_10_13_08-15-48_w.mp4` | 1,402,211 | `329477efbde5cec6294e3a0886929a80b5348ddbd3c65bdbd71bd999e3931125` | H.264, 1920×1080, 192 frames, time base 1/90000, average rate 5760000/287483, container duration 9.582767 s |

Opening an original creates the product's adjacent
`.mp4.labelimgpp.sqlite` sidecar. That expected project-file behavior was
observed; the original MP4 hashes above remained the source identity. All
drawing and propagation work described below used the retained acceptance
copies.

## Real OS-level workflow

The app was launched through a uniquely identifiable macOS wrapper
(`org.labelimgplusplus.acceptance`). All direct UI operations were performed
through the macOS computer-use accessibility/screenshot interface. Terminal
use was limited to installing the declared extra, launching the app, running
tests, and validating evidence files.

| Check | V1 | V2 | V3 |
| --- | --- | --- | --- |
| Open original, then acceptance copy | Pass | Pass | Pass |
| Full frame visible with Fit Window selected | Pass | Pass | Pass |
| A/D previous/next frame | Pass | Pass | Pass |
| Semantic Play → Pause control state | Pass | Pass | Pass |
| Mouse timeline seek | Pass | Pass | Pass |
| Keyboard timeline seek | Pass | Pass | Pass |
| Accessibility slider value seek | Pass | Pass | Pass |
| Canonical exact time `00:00:02.000` | Pass | Pass | Pass |
| Out-of-range `99:00:00.000` retained with focus and no seek | Pass | Pass | Pass |
| Select `car` once and draw two rectangles | Pass | Pass | Pass |
| Sole-owner continuous-save status reaches `Saved` | Pass | Pass | Pass |
| Verify current frame | Pass | Pass | Pass |
| Close and reopen saved SQLite project | Pass | Pass | Pass |
| Start propagation; use visible named Cancel action | Pass | Pass | Pass |
| Pending review; named Accept, undo, named Reject | Pass (574) | Pass (81 accept; 206 reject) | Pass (382) |
| 10 open/play/seek/close cycles | Pass | Pass | Pass |
| Essentials at actual 800-pixel outer width | Pass | Pass | Pass |

For V2, the real Cancel click arrived after the fast local tracker had already
completed its 206-frame span; the control was visibly invoked, but there were
no unresolved gaps. V1's earlier cancelled run retained 59 pending results,
and V3 displayed live progress (`16/192 frames · 1 active · 0 complete`) before
its visible Cancel action. Deterministic automation separately holds the
worker until cancellation and asserts both pending observations and unresolved
gaps, avoiding machine-speed dependence.

The line edit's Qt validator rejects noncanonical letters before they enter the
widget, so typing `invalid` through real OS key events cannot leave an invalid
string on screen. The real invalid state therefore uses the accepted-shape but
out-of-range value `99:00:00.000`: focus stays on `Exact video time`, the value
is retained, and the frame does not move. Automated coverage injects
`not-a-time` below the native validator boundary and asserts the same error
contract for malformed input.

At an actual 800-pixel outer window width, the compact controls stayed usable.
The 30-cycle soak ran in that wrapper and covered every unique copied project;
V3 also repeated A/D, play/pause, mouse drag, Home seek, accessibility value
seek, canonical and out-of-range time, save, and verify at that width.

## Accessibility evidence and UX observations

Fresh accessibility trees exposed and confirmed these stable names and state
changes:

- `Video timeline` (settable slider) included accepted, pending, verified, and
  propagation marker descriptions; value updates sought the decoded VFR frame.
- `Previous frame` / `Next frame` exposed the A/D shortcuts.
- `Play video` changed to `Pause video` while playing and back after pausing.
- `Exact video time` exposed `Exact presentation time (HH:MM:SS.mmm)`; invalid
  submission kept focus, while a valid submission returned focus to canvas.
- `Fit Window` remained checked after open and resize.
- `Accept propagated results`, `Reject propagated results`, and `Cancel` were
  visible named actions in their corresponding states.
- The status projection exposed `Saved`, verification state, source dimensions,
  object count, and zoom.

The compact `Track` and `More commands` QToolButtons sometimes accepted an AX
click only as focus without opening their Qt popup. The native `T` shortcut and
wide, directly named review controls remained usable. This is recorded as an
accessibility-automation limitation/UX follow-up; it did not block mouse or
keyboard use. The semantic play/pause and settable timeline controls worked
reliably through AX.

## Screenshot matrix

Evidence lives in
`docs/screenshots/video-workspace-2026-08-24/`. Each file is a real Qt product
window using a decoded frame from a supplied video; no painted mock is used.

The five 800×600 states `paused`, `playing`, `invalid-time`,
`propagation-progress`, and `pending-review` are real computer-use captures
from the exact 800×628 macOS window, cropped only by the 28-pixel titlebar to
the true 800×600 client. Three 800×600 states are deterministic real-widget
surrogates: the live Qt `Track` menu (popup capture was unreliable through the
compact AX button), missing-runtime setup (PyAV was installed for acceptance),
and shutdown timeout (the natural run did not fail, so no timeout was induced).
The other 24 files are deterministic, exact-size real-Qt captures because the
macOS window manager held the live wrapper at 800×628 or 1296/1306×768 instead
of the requested 960×640, 1366×768, and 1440×900. Surrogates render the actual
widgets and decoded frame, not a synthetic painting.

| File | Source | SHA-256 |
| --- | --- | --- |
| `compact-track-menu-800x600.png` | real-Qt surrogate | `59eaf9c7acdef0260e24d030f45195eab0431f0419050f3a290f6778374b91a9` |
| `compact-track-menu-960x640.png` | real-Qt surrogate | `f53ca28a2cbbbef9775b920cff5f2be365e19e639573059985932382f88310f2` |
| `compact-track-menu-1366x768.png` | real-Qt surrogate | `909443fd95d35a33277dc1abd0edabb541f6932a57c9761e5afb4c47311c33b7` |
| `compact-track-menu-1440x900.png` | real-Qt surrogate | `32dca56947c6b1fadc9b0b44d56387bcb485274e366b3ffb57f8f8d638ac72e7` |
| `invalid-time-800x600.png` | computer use | `213d7ffc01b287d73f5bd81abc5dcd0ee0f5eb2deb8fa2bcc582c249aed20545` |
| `invalid-time-960x640.png` | real-Qt surrogate | `97f9fd19e5f0249cf43d72e04860062534a700557922457344b8b2dc125746a2` |
| `invalid-time-1366x768.png` | real-Qt surrogate | `0f512523a8325a6bcaec3ec0e3b1350dcf56031ad514275535b529954e7b45a3` |
| `invalid-time-1440x900.png` | real-Qt surrogate | `323b0e2183d86c5f0d4343252c744f9336f80e46afef5ca1e64211b52955f931` |
| `missing-runtime-setup-800x600.png` | real-Qt surrogate | `af54f0e0d5f3e1287561232c1a1c069493831572ae98972337c00bb7520fc500` |
| `missing-runtime-setup-960x640.png` | real-Qt surrogate | `ab0d88a41cb24bd69444aae09f79cae509eb14066f48d2c2907d91f8f4a1771b` |
| `missing-runtime-setup-1366x768.png` | real-Qt surrogate | `5d920bdaad214a6873365ddd23e780247984b840e18d4fdf63faae85f776c35c` |
| `missing-runtime-setup-1440x900.png` | real-Qt surrogate | `b3b40283452bb6b728f32cb462510bddf91319945fae02a26134d5b7fd20f297` |
| `paused-800x600.png` | computer use | `c2323de9afbaaef7eb6bdfc4de6de5c723445b19f1c260ff9b334f3512960284` |
| `paused-960x640.png` | real-Qt surrogate | `6b3ec900fb7be02895619d8f61dc951650b6bcf20e34fd81d455cbc23b8cd578` |
| `paused-1366x768.png` | real-Qt surrogate | `1a2e1fde0c8f3417c9336edd9e7b3edaa1cd6716ea8d3e7e1b6174470923660b` |
| `paused-1440x900.png` | real-Qt surrogate | `72ac9012071fe9ab2dca13c3cba08ff503fd6dbf069bc0938b482e607de15d7a` |
| `pending-review-800x600.png` | computer use | `008b825cd0e46b257acba0e00a3f8d3d35ecb145b3b8cdc550a887d5301bdad9` |
| `pending-review-960x640.png` | real-Qt surrogate | `05a3a250c3b2f24e112290000456d10c268c36883b09818484a638d5d99981b1` |
| `pending-review-1366x768.png` | real-Qt surrogate | `8483778719666bcd32b91da36434e73787313810d77fb36e5334794f669b6dbe` |
| `pending-review-1440x900.png` | real-Qt surrogate | `6a6356b7a9f4ab6c5300757ec3373d4720bb7f6951e9f7001b7adf3efbcc6dfa` |
| `playing-800x600.png` | computer use | `8a29d9980b68ea7d01f4f71fa6980733987b4c15a72854a11b64a04c6dad174a` |
| `playing-960x640.png` | real-Qt surrogate | `6271aab5418a2d9d7a997ab9777be3ed0e7d1494f0102edc5301fdf140bd4770` |
| `playing-1366x768.png` | real-Qt surrogate | `130204a36ccbb02367e9517b7a65c7f20e7d96717eac0adc00e41a37c1a4a32e` |
| `playing-1440x900.png` | real-Qt surrogate | `60751bd6843ee51d80249da0cc43c403ec4c5422b5b971e08afc52af3ca568fb` |
| `propagation-progress-800x600.png` | computer use | `84144124f19468cbbaebefedab9137f2fcc8dbdd9e5d811f657d8b7bfd9e610a` |
| `propagation-progress-960x640.png` | real-Qt surrogate | `ed98e71dea36511a11d368bd0dab9d137cafc3eb5038ae397efb342a732c8131` |
| `propagation-progress-1366x768.png` | real-Qt surrogate | `293f0b1eb69b00f5ad31942eae8dff91410ffd1cd7e3d74942044aa08161ded0` |
| `propagation-progress-1440x900.png` | real-Qt surrogate | `8123852c47400e5262d83eaab1480818d74211dee831bb72a75fec6d604468a7` |
| `shutdown-timeout-800x600.png` | real-Qt surrogate | `03b93100f9c01fdd385215766aea0b8283728e7b409de4f07896545099b19c31` |
| `shutdown-timeout-960x640.png` | real-Qt surrogate | `967b3e9ef5e351e1ef16e2977da165661ecc206acd3457a0b9da967663e926b9` |
| `shutdown-timeout-1366x768.png` | real-Qt surrogate | `4e9987515ffc86e456f9f6f86dbef714fdc0cff1304149f573d109fb2ffc1573` |
| `shutdown-timeout-1440x900.png` | real-Qt surrogate | `2e9c74c60c44ac7a404a7ce4d50384d3f674c7831b3dc9eddc539694deaba743` |

Validation asserted exactly 32 PNGs, a nonzero decoded image for every file,
more than 1,000 bytes per file, and dimensions equal to each filename.

## Repeatable checklist

1. Install the declared video extra with `python -m pip install -e '.[video]'`.
2. Hash and probe each unique original; open it once and confirm a fitted full
   1920×1080 frame. Copy the MP4 before annotation if the original must remain
   free of project-side effects.
3. On the copy, use A and D; play and pause; mouse-drag the timeline; use Home
   or Page Down on the focused slider; set its accessibility value; enter
   `00:00:02.000`, malformed text, and `99:00:00.000`.
4. Select one class, turn off per-object confirmation, draw two rectangles,
   wait for `Saved`, verify the frame, close, and reopen the SQLite project.
5. Start tracking, cancel while active, and inspect pending count and gaps. Run
   again, activate `Accept propagated results`, undo, then activate
   `Reject propagated results`.
6. Repeat open → play → pause → seek → close ten times for each unique project;
   confirm clean close and no queued video work.
7. Resize to an actual 800-pixel outer width and repeat the essential
   open/play/seek/close interaction. Inspect the compact Track access.
8. Check fresh AX names/focus, the terminal exit status, macOS diagnostic
   reports, and the 32 screenshot filenames, dimensions, and hashes.

## Automated acceptance

`tests/video/test_workspace_flow.py` makes the flow deterministic. It covers a
transactional failed replacement, fit, buttons and A/D stepping, semantic
play/pause, mouse/keyboard/accessibility seek, valid/malformed/out-of-range
time, choose-once/draw-twice, sole-owner Saved, Verify, project reopen,
cancelled propagation with pending results and gaps, accept/undo/reject, and a
bounded ten-cycle decoder/task shutdown soak.

The initial RED proof was an absent test module (`pytest` collection exit 4).
The added flow passes with the optional runtime enabled. The final focused,
video/coordinator/command-bar, staged-snapshot, and full-repository results are
recorded in the Task 7 implementer report.
