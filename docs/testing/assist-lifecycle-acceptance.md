# Assist lifecycle acceptance — 2026-08-25

## Result

The Assist lifecycle passed its deterministic offline gate and one native
real-provider pass. Download did not start until the visible action was chosen;
Cancel waited for worker cleanup, left no `.part`, and did not retry during a
30-second observation. The explicit retry produced a manifest-valid MobileSAM
cache. Real image and supplied-video inference stayed provisional until Reject
or Accept, acceptance used Active class and reached Saved, and video propagation
did not start until **Track forward** was chosen explicitly.

The fake provider in `tests/integration/test_assist_flow.py` is intentionally an
orchestration seam only. It coordinates progress, cancellation, cleanup, retry,
and controlled external inference without weakening the real size/SHA boundary
owned by `model_cache` and the live manifest check below.

## Isolated live environment

- Native wrapper: `/tmp/LabelImgPlusPlusTask6Native.app`, bundle identifier
  `com.labelimgplusplus.task6.native`.
- Cache: `/tmp/labelimgpp-task6-live/cache/labelimgpp`.
- Project and generated annotations:
  `/tmp/labelimgpp-task6-live/project`.
- Settings: `/tmp/labelimgpp-task6-live/settings/live-settings.json`.
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
| Storage | `/tmp/labelimgpp-task6-live/cache/labelimgpp` |

The visible **Download model** action started the real transfer. Progress
reached 9,437,184 bytes on `mobile_sam.encoder.onnx`, then the visible
**Cancel** action was chosen. The encoder happened to complete its atomic
validation/promotion before cancellation landed, so that valid final file was
retained; the decoder never started, the worker returned to **Ready to
download** only after cleanup, and there was no incomplete artifact. A fresh
30-second accessibility/state observation showed the same file set, no
decoder, no `.part`, and no automatic retry.

The second visible **Download model** action completed the missing artifact.
`cached_model_paths()` returned both paths and the final files matched the
immutable provider manifest exactly:

| Artifact | Bytes | SHA-256 | Result |
|---|---:|---|---|
| `mobile_sam.encoder.onnx` | 28,157,203 | `801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45` | Match |
| `mobile_sam.decoder.onnx` | 16,501,737 | `001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8` | Match |

The post-check found `parts=[]`. The first relaunch also truthfully projected a
typed runtime failure because the native wrapper could not see the task-local
ONNX Runtime directory. Adding that directory only to the temporary wrapper's
`LSEnvironment` recovered to Ready without downloading again.

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
| Post-accept | `post-accept-track-forward-{size}.png` | Manual-anchor copy and Track forward |
| Closed Assist | `assist-closed-{size}.png` | Panel absent; canvas focused |

The screenshot integrity gate loaded all 24 files through `QImage`, verified
every file was nonempty, verified all 20 controlled PNG dimensions against the
filename, and recorded SHA-256 digests. The four native JPEGs were each
1295×768 and 301,035–307,410 bytes.

## Deterministic RED / GREEN and offline gates

- RED: the first complete lifecycle node reached the saved manual anchor but
  failed because Track Forward was hidden. Exact call-order isolation showed
  that fake ONNX bytes reached the real controller prepare path and correctly
  projected setup-required instead of pretending to be ready.
- GREEN: the harness now substitutes only the external inference runtime while
  keeping real MainWindow, state, cache paths, worker coordination, prompt,
  preview, reject/accept, video model, save, and propagation ownership. The
  focused file passes `3 passed`.
- The native QAction/overlay regression initially reproduced a panel that was
  logically visible but painted behind the stacked workspace. After the
  independently reviewed Task 3 overlay fix, the exact native user path is
  GREEN and remains in `test_smart_select_action_opens_visible_focused_assist`.
- Network-disabled aggregate:
  `96 passed, 3 skipped in 5.45s` across Task 1–6 Assist state, manifest, cache,
  segmentation, backend, panel, canvas, controller, MainWindow, and the Task 6
  flow. A `sitecustomize.py` socket sentinel rejected outbound socket creation.

The bounded integrated hardening, Python 3.8, Ruff F, screenshot, diff, and
exact-index results are recorded in the Task 6 SDD report.
