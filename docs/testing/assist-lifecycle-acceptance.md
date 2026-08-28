# Assist lifecycle acceptance — 2026-08-25

## Result

The Assist lifecycle passed its deterministic offline gate and one native
real-provider pass. Download did not start until the visible action was chosen;
Cancel waited for worker cleanup, left no `.part`, and did not retry during a
30-second observation. The explicit retry produced a manifest-valid MobileSAM
cache. Real image and supplied-video inference stayed provisional until Reject
or Accept, acceptance used Active class and reached Saved, and video propagation
did not start until **Track forward** was chosen explicitly.

The controlled acquisition provider and external fake inference backend in
`tests/integration/test_assist_flow.py` are intentionally orchestration seams
only. The test retains the real `SamController`, `TaskCoordinator` SAM lane,
worker signals, prompt ordering, result generation, state, and MainWindow
review/save flow. Real size/SHA validation remains owned by `model_cache` and
the live manifest check below.

## Isolated live environment

- Final provider wrapper: `/tmp/LabelImgPlusPlusTask6Fix1C.app`, bundle
  identifier `com.labelimgplusplus.task6.fix1c`.
- Final provider cache:
  `/tmp/labelimgpp-task6-fix1-live-20260825T182920Z/cache/labelimgpp`.
- Final provider project/settings:
  `/tmp/labelimgpp-task6-fix1-live-20260825T182920Z/project` and
  `/tmp/labelimgpp-task6-fix1-live-20260825T182920Z/settings/settings.json`.
- The earlier real image/video flow used the separate task-local
  `/tmp/labelimgpp-task6-live` project/cache and native wrapper; the two runs
  did not share user state.
- Optional runtime: task-local `/tmp/labelimgpp-task6-live-venv`; no base
  dependency or user model cache was changed.
- Image document:
  `tests/fixtures/臉書.jpg`.
- Supplied video opened read-only first, then copied for mutation to
  `/tmp/labelimgpp-task6-live/project/video-copy/000414_000480_2025_09_04_17-49-10_w.mp4`.
  The source and acceptance copy both had SHA-256
  `04e6148c003d7e29a8dd7900af988855eb9e50d46bbe3424c37d6e0f756941a5`.
  The source MP4 remained 10,351,896 bytes with mtime `1757010289`; its
  pre-existing adjacent SQLite sidecar remained 81,920 bytes with mtime
  `1787579289` across the before/after checks. All accepted and propagated
  observations were written only beside the task-local copy.

All native UI actions were performed through persistent `node_repl` and
`@oai/sky`; shell checks were read-only validation or task-local setup.

## Real provider acquisition

The empty-cache setup UI exposed these details before any network work:

| Field | Observed value |
|---|---|
| Purpose | Turn box or point prompts into object masks |
| Provider | LabelImg++ GitHub Releases |
| Download size | 42.6 MB / 44,658,940 bytes |
| Storage | `/tmp/labelimgpp-task6-fix1-live-20260825T182920Z/cache/labelimgpp` |

The visible **Download model** action started the bounded cancellation run at
22:17:13Z. The visible **Cancel** action was chosen at 22:17:14Z, the panel
truthfully showed **Cancelling…**, and it returned to **Ready to download** only
after worker cleanup. Filesystem snapshots at 22:17:28Z and 22:18:22Z were both
empty with no `.part`; an independent UI observation at 22:18:07Z remained
Ready, proving there was no automatic retry for more than 30 seconds.

Explicit Retry was chosen only after that observation. The real provider
exposed successively corrected finite-timeout/reuse boundaries while retaining
cleanup on every failure. On reviewed HEAD `fbc74b4`, a full native process
restart preserved the valid encoder and missing decoder. The explicit Retry at
22:52:15Z reused the encoder unchanged, requested only the decoder with 64 KiB
reads and a finite 10-second idle bound, and reached Ready at 22:52:33Z.
`cached_model_paths()` returned both paths; no `.part` remained; and the final
files matched the immutable provider manifest exactly:

| Artifact | Bytes | SHA-256 | Result |
|---|---:|---|---|
| `mobile_sam.encoder.onnx` | 28,157,203 | `801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45` | Match |
| `mobile_sam.decoder.onnx` | 16,501,737 | `001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8` | Match |

The encoder mtime remained `1787696443` before and after the decoder-only
retry, providing direct evidence that it was reused rather than downloaded
again. The full timestamped AX/filesystem transcript, including the main
Cancel, cleanup, 30-second no-retry observation, explicit retries, and final
hashes, is retained in
[`provider-cancel-retry-transcript.md`](../screenshots/assist-lifecycle-2026-08-25/provider-cancel-retry-transcript.md).

## Native preview, accept, save, and tracking flow

### Image

1. Assist opened on the editable image with **Smart Box** and **Smart Points**
   visible.
2. **Smart Points** plus a positive point produced a real MobileSAM preview.
3. **Reject** returned to `Saved`, `Objects: 0`; no canonical object appeared.
4. A second positive point plus an explicit negative point visibly refined the
   mask while it remained provisional.
5. Active class was set to `car`; **Accept** produced one polygon and the status
   reached `Saved`, `Objects: 1`.

### Supplied video

1. The native Open Video dialog opened the supplied file. Its existing adjacent
   user sidecar was detected before mutation, so the flow was restarted on the
   byte-identical task-local copy; that copy began at `Saved`, `Objects: 0`, and
   `No timeline markers`.
2. Real MobileSAM prepared the 1920×1080 frame and produced a provisional
   polygon. **Reject** returned to `Saved`, `Objects: 0`.
3. A second preview was accepted with Active class `car`. The UI reached
   `Saved`, showed one accepted manual polygon at range 0, and displayed:
   “Accepted as a manual anchor. Track it forward when you are ready.”
4. A five-second observation produced no accessibility or timeline change.
   Only the explicit **Track accepted Assist result forward** action started
   propagation.
5. Tracking completed at 150 pending results, zero gaps, and zero failures.
   Results remained in pending review; they were not silently accepted.

The macOS file picker exposed one computer-use limitation: after that dialog,
raw coordinate click/drag calls returned `noWindowsAvailable` although the
window remained fully available to accessibility actions and screenshots. A
safe `@oai/sky` AX click on the native standard-window element activated and
clicked its center, which lay inside the canvas, and completed the real prompt
flow. No alternate OS automation technology was used.

## Accessibility and focus evidence

The native accessibility tree exposed one contextual surface with these names:

- `Assist`, `Close Assist`, and `Assist model download progress`;
- `Download Assist model`, `Cancel Assist model download`, and
  `Retry Assist setup`;
- `Use Smart Box` and `Use Smart Points`;
- `Accept Assist preview` and `Reject Assist preview`; and
- `Track accepted Assist result forward`.

The committed workspace accessibility gate also verifies `Annotation canvas`,
`Active annotation class`, `Filter annotations by class`, `Search
annotations`, `Annotations`, `Filter files by annotation status`, `Dataset
files`, `Inspector`, and `Dataset gallery`.

Opening Assist focused the state heading (`Set up Assist`, `Ready to download`,
`Choose an Assist tool`, `Creating preview`, or `Review preview` as applicable).
The native overlay regression verifies that the panel is visible above the
workspace page. The controlled closed-Assist capture verifies the panel is
hidden and focus is returned to the canvas.

## Screenshot evidence

The physical computer-use capture was 1295×768, so a native 1366-pixel-wide
window was not available. The four retained native JPEGs are therefore kept at
their truthful 1295×768 size and were never resized:

- `docs/screenshots/assist-lifecycle-2026-08-25/video-preview-live.jpeg`
- `docs/screenshots/assist-lifecycle-2026-08-25/video-accepted-track-forward-live.jpeg`
- `docs/screenshots/assist-lifecycle-2026-08-25/video-tracking-running-live.jpeg`
- `docs/screenshots/assist-lifecycle-2026-08-25/video-tracking-review-live.jpeg`

For the exact review contract, the production Qt window and real `AssistPanel`
were rendered deterministically offscreen. These are controlled lifecycle
states, not resized or fabricated live-provider states. Each pattern below
exists once at 800×600 and once at 1366×768 under
`docs/screenshots/assist-lifecycle-2026-08-25/`:

| State | Artifact pattern | Truthful visible action/copy |
|---|---|---|
| Setup required | `setup-required-{size}.png` | Purpose/provider/path/size and Download |
| Ready to download | `ready-to-download-{size}.png` | Download; no network started |
| Downloading | `downloading-cancel-{size}.png` | Progress and Cancel |
| Offline failure | `offline-failure-{size}.png` | Offline guidance and Retry |
| Validation failure | `validation-failure-{size}.png` | Validation guidance and Retry |
| Ready | `ready-{size}.png` | Smart Box and Smart Points |
| Running | `running-{size}.png` | Unchanged-document copy and indeterminate progress |
| Preview | `preview-{size}.png` | Paint-only polygon, Accept, and Reject |
| Post-accept | `post-accept-track-forward-{size}.png` | Real task-local video model with one accepted manual anchor/timeline marker; full Smart Box, Smart Points, and Track forward actions; no propagation |
| Closed Assist | `assist-closed-{size}.png` | Panel absent; canvas focused |

The screenshot integrity gate loaded all 24 files through `QImage`, verified
every file was nonempty, verified all 20 controlled PNG dimensions against the
filename, and recorded SHA-256 digests. The four native JPEGs were each
1295×768 and 301,035–307,410 bytes.

## Deterministic RED / GREEN and offline gates

- RED: after removing the direct `SamController.run_prompt` monkeypatch and
  direct MainWindow preview injection, the controlled external inference
  backend lacked the planned `prepare_mask` coordination point and the real
  controller lifecycle failed with `AttributeError`. This proved the test was
  traversing the controller rather than publishing a preview itself.
- GREEN: the backend now blocks and releases deterministic masks through its
  external `set_image`/`predict` boundary. Real `SamController`,
  `TaskCoordinator` SAM lane, worker signals, prompts, `SamResult` polygon
  generation, MainWindow state, preview, reject/accept, video model, save, and
  explicit propagation ownership remain exercised. The focused file passes
  `3 passed`; the release-finding compatibility/accessibility selection passes
  `7 passed`.
- The native QAction/overlay regression initially reproduced a panel that was
  logically visible but painted behind the stacked workspace. After the
  independently reviewed Task 3 overlay fix, the exact native user path is
  GREEN and remains in `test_smart_select_action_opens_visible_focused_assist`.
- Network-disabled aggregate:
  `109 passed, 2 skipped in 33.34s` across Task 1–6 Assist state, manifest,
  cache, segmentation, backend, panel, canvas, controller, MainWindow, and the
  Task 6 flow. A `sitecustomize.py` socket sentinel rejected outbound network
  connections. The count replaces the stale 96/97 evidence after the reviewed
  provider fixes and release-finding regressions were collected. The exact
  staged-index export repeated the same result in `29.50s`.
- A fresh-process segmented release gate exercised every one of the `1,338`
  collected nodes from the exact staged-index export. Non-plugin segments
  passed `1,300` nodes with `3` optional skips; four plugin-sensitive files ran
  in separate normal-environment processes and passed their remaining `35`
  nodes. Corrected total: `1,335 passed, 3 skipped, 0 failed`.

The bounded integrated hardening, Python 3.8, Ruff F, screenshot, diff, and
exact-index results are recorded in the Task 6 SDD report.
