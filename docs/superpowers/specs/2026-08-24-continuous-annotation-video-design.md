# Continuous Annotation and Video Workspace Design

**Date:** 2026-08-24

**Status:** Approved in chat; written specification awaiting review

**Scope:** Image annotation, VFR video annotation, contextual AI assistance,
responsive layout, persistence, and recovery

## Product goal

LabelImg++ must be the easiest desktop annotation application to begin using
and the fastest to continue using. It should combine Labelme's clear dataset
position and explicit model feedback with AnyLabeling's continuous drawing
workflow, while providing substantially stronger video support and recovery
than either application.

The default workflow is throughput-oriented:

1. Open content and see the complete frame.
2. Choose a class once.
3. Choose a drawing tool once.
4. Draw repeatedly without recurring confirmation.
5. Navigate without losing class, tool, view mode, or work.

Users who require per-shape confirmation can enable that policy without
changing annotation formats or the rest of the workspace.

## Evidence behind the design

The live comparison used the same four frames extracted from a supplied video
in Labelme 7.1.0, AnyLabeling 0.4.36, and the current LabelImg++ remediation
worktree. LabelImg++ was also exercised with the supplied VFR videos.

- Labelme exposes queue position and direct keyboard navigation well, but uses
  modal class confirmation, becomes dense at full size, hides AI tools at
  smaller heights, and continued model-download retries after visible cancel.
- AnyLabeling retains its drawing mode across files and restores annotations
  after restart, but still prompts for a class, enforces a wide minimum layout,
  hides AI in toolbar overflow, and produced a blank busy workspace during the
  model-control recovery pass until restart.
- LabelImg++ has accurate VFR stepping, working playback, persisted review
  state, and a cleaner shell. Its live friction came from stale canvas fitting,
  transient drawing tools, an obscure default-label checkbox, delayed saving,
  clipped compact video controls, inaccessible seeking, invalid time input,
  and AI controls that were disabled without explaining how to enable them.

The current remediation specification deliberately preserves transient
rectangle creation and autosave-on-navigation. This design supersedes those
two decisions; all unrelated remediation requirements remain in force.

## Success criteria

### First-use success

- A new user can open an image directory or video, draw the first labeled
  object, advance, and continue without opening Preferences or documentation.
- Opening content displays the complete image or video frame after the final
  window layout is established.
- Every unavailable feature explains what it needs and offers a direct next
  action. No primary tool is silently disabled.

### Repeated-work success

- The active class and active drawing tool survive image navigation and video
  frame navigation.
- A completed annotation is durably saved without waiting for navigation.
- The next frame is reachable with `D`; the previous frame is reachable with
  `A`; focus returns to the canvas after transient editors close.
- Exactly one tool appears active at every moment.

### Video success

- Variable-frame-rate stepping remains PTS-accurate.
- Playback, mouse seeking, keyboard seeking, assistive-technology seeking,
  exact-time seeking, verification, annotation, propagation, save/reopen, and
  clean shutdown work on every supplied unique video.
- Essential transport and time controls remain visible at an 800-pixel window
  width. Secondary detail may collapse but must remain discoverable.
- Repeated open/play/seek/close cycles do not crash Python or leave decoder,
  model, or download workers running.

## Interaction architecture

The existing Qt shell remains. The change introduces three focused state
owners instead of adding more conditional state to `MainWindow`.

### Annotation workflow state

A small framework-independent workflow model owns:

- `active_class`: the class applied to the next accepted result;
- `prompt_policy`: `reuse_active` by default or `confirm_each`;
- `active_tool`: Select, Rectangle, Polygon, Smart Box, or Smart Points;
- whether incomplete provisional geometry exists.

The canvas remains authoritative for low-level geometry mode. `MainWindow`
projects workflow intent into the canvas and actions through one synchronization
method. Document loading never resets `active_class` or `active_tool`; closing
the dataset resets both. Escape cancels provisional geometry first, then returns
to Select when no provisional work remains.

The visible inspector control becomes **Active class**, not **Use default
label**. Selecting a class establishes it immediately. With `reuse_active`, a
completed manual shape commits with that class and the tool stays armed. If no
class exists, the inline class picker opens. Clicking a picker result commits
immediately; typing and pressing Return does the same. With `confirm_each`, the
picker opens after every completed shape.

### Continuous save state

A save coordinator owns these states: `saved`, `pending`, `saving`, and
`failed`. Mutation boundaries notify it with the current document revision.
Those boundaries include shape commit, completed geometry edit, relabel,
delete, verification, accepted AI result, propagation acceptance, undo, and
redo. Pointer-move events may mark a revision dirty but are coalesced.

The coordinator waits 250 ms after the latest mutation, then calls the existing
image or video save lane. If another mutation occurs during a save, it schedules
the newest revision immediately after completion. Late completion may mark only
the revision it actually wrote as durable. The status copy is exactly:

- `Saving…`
- `Saved`
- `Save failed · Retry`

Image sidecars are written to a temporary file in the destination directory,
flushed, and promoted with `os.replace`; a failed write cannot corrupt the last
durable annotation. Video projects retain their existing revisioned snapshot
contract and gain the same atomic destination promotion guarantee where it is
not already present.

Image navigation flushes unsaved state before replacing the current image.
Because ordinary edits save continuously, this should normally be a no-op.
Video frame navigation may continue while an immutable project snapshot saves;
opening another document or quitting waits for the newest revision. Save
failure keeps the document dirty, preserves all in-memory edits, and prevents a
destructive document switch until Retry succeeds or the user explicitly
chooses Discard.

The two existing autosave concepts are consolidated into one **Save changes
automatically** preference, enabled by default. Existing installations with
navigation autosave enabled migrate to enabled. Timer interval settings remain
readable for compatibility but disappear from the primary workflow. When the
preference is disabled, Save is explicit and navigation follows the existing
Save/Discard/Cancel safeguard.

### View transform state

View mode is one of `fit_window`, `fit_width`, or `manual`. The checked action,
zoom value, canvas scale, and scroll ranges are projections of that single
mode.

- Opening a new dataset or video starts in `fit_window`.
- Image navigation preserves the chosen mode. Fit modes recalculate after the
  new pixmap and final canvas geometry are available. Manual mode preserves its
  zoom percentage and centers the new image within valid scroll bounds.
- Video frame changes preserve zoom and pan because frame dimensions are stable.
- Switching documents starts a fresh `fit_window` session.
- A deferred scale projection runs once on the next Qt event turn after initial
  layout, preventing pre-inspector dimensions from producing a clipped frame.

## Core manual flow

### Opening

The existing Open menu continues to accept images, directories, annotations
through their source image, videos, and video projects. The command bar shows a
short filename and queue position. Its tooltip exposes the complete path.
Opening failure leaves the current document painted and editable, then shows an
inline error with Retry or Choose another file.

### Drawing

Rectangle uses drag-to-create. Polygon uses click-to-add and the existing close
gesture. After commit:

- the shape receives the active class;
- it appears in the inspector without switching the canvas to Select;
- the drawing tool remains active;
- continuous saving is scheduled;
- canvas focus is restored.

The new shape receives a short visual highlight but not edit handles. Selecting
an existing shape explicitly enters Select. This prevents the next drag from
accidentally resizing the object while preserving immediate edit access.

### Navigation

`A` and `D` operate whenever a transient text editor is not intentionally
accepting text. A valid class or time submission returns focus to the canvas.
If navigation is requested while incomplete geometry exists, the geometry is
cancelled, committed annotations are preserved, and a non-blocking `Draft
discarded` message appears. A visible class picker counts as incomplete work
and is cancelled rather than guessed.

## Responsive workspace

The layout responds to available workspace width rather than screen width.

- At 960 logical pixels or wider, the inspector remains a docked column.
- Below 960 logical pixels, the inspector becomes a canvas-overlay drawer. It
  starts closed for the session and is opened through the existing inspector
  affordance, which shows the object count.
- Crossing the breakpoint does not overwrite the user's persistent inspector
  preference. Returning to wide mode restores that preference.
- Canvas, timeline, command bar, and status layouts have zero artificial
  minimum width. Essential actions receive space before labels and secondary
  metadata.

The status strip prioritizes save state, verification, object count, and zoom.
Long paths and diagnostic detail use middle elision plus complete tooltips.

## Video workspace

### Responsive timeline

The timeline has two logical rows:

1. a full-width seek track with accepted, pending, verified, and propagation
   markers;
2. transport and context controls.

Transport priority is Previous frame, Play/Pause, Next frame, exact time, and
speed. The primary position reads `Frame ~N · HH:MM:SS.mmm`. Raw PTS remains in
the tooltip and diagnostic surfaces. At compact width, propagation actions move
into a named **Track** menu and secondary labels elide; transport, time, speed,
and the seek track never disappear.

The command bar uses **Previous document** and **Next document** terminology.
It never describes video navigation as image navigation.

### Seek and playback semantics

The timeline distinguishes internal position projection from user intent.
Internal frame updates block seek emission. Mouse release, keyboard changes,
and accessibility value changes all emit a debounced `seekRequested` with an
immutable `VideoFrameRef`. Dragging may update at most every 50 ms and always
emits the final release value.

Exact time accepts `HH:MM:SS.mmm` only. Minutes and seconds must be between 0
and 59; the resulting time is clamped to the video range. Return seeks and
returns focus to the canvas. Escape restores the current frame time and returns
focus to the canvas. Invalid input shows an inline error and never resets to the
video's initial frame.

The transport action exposes `Play video` while paused and `Pause video` while
playing through its accessible name, tooltip, icon, and checked/state
description. Reaching the end returns to the paused state. Frame stepping first
pauses playback and then resolves the exact neighboring PTS.

### Propagation

Propagation is contextual. **Track selected object** is enabled only for an
accepted manual anchor. **Track all anchors** remains available from the Track
menu. Progress replaces those commands with processed frames, active tracks,
completed tracks, ETA, gaps/failures, and a real Cancel action. Cancel stops
workers, keeps already accepted durable results, marks unresolved spans as
gaps, and restores editing without requiring restart.

## Contextual AI assistance

The Smart Select rail entry is enabled whenever a document can be annotated,
even when no model is installed. Activating it opens a contextual **Assist**
surface with one of these explicit states:

- setup required;
- ready to download;
- downloading;
- ready;
- running;
- preview;
- failed.

Setup explains the selected model's purpose, provider, storage location, and
download size before network work starts. Download begins only after the user
chooses it. Progress offers Cancel; cancellation stops network and worker
activity, removes the incomplete temporary artifact, and never retries in the
background. Completed files are moved atomically into the model cache. Failure
offers Retry and preserves the document.

Smart Box and Smart Points create provisional results. Results do not mutate
the document until accepted. Enter accepts, Escape rejects, and prompt gestures
refine the preview. An accepted result uses the active class or opens the same
inline class picker when none exists, then enters the continuous save lane. On
video, acceptance additionally offers **Track forward**; propagation never
starts merely because an AI result was accepted.

AI controls are contextual rather than permanently occupying the command bar.
Closing Assist cancels only provisional prompts and inference, not accepted
annotations or completed model downloads.

## State and data flow

```text
User gesture
  → Annotation workflow state
  → Canvas provisional geometry or AI preview
  → Class resolution
  → Annotation/video model mutation + undo command
  → Document revision
  → Continuous save coordinator
  → Atomic image save or versioned video-project save
  → Saved / failed projection in command bar and status strip
```

Document state is never inferred from painted widgets. Canvas actions, class
controls, timeline controls, save presentation, and inspector presentation are
projections of their respective state owners. Async callbacks carry dataset
generation and document revision so stale work cannot replace a newer document
or mark a newer revision saved.

## Error and shutdown behavior

- Image, video, project, model, and annotation open failures preserve the
  current workspace until the replacement is ready.
- Decoder creation, first-frame decoding, model import, model download, and
  propagation remain outside the GUI thread. Publishing Qt images and widgets
  remains on the QApplication thread.
- Closing a document cancels decode, prefetch, inference, propagation, and
  download workers associated with its generation.
- Quit waits for the latest save revision and bounded worker shutdown. If save
  fails, Save/Discard/Cancel is shown. Discard is never chosen automatically.
- Worker completion after close is ignored through generation checks.
- Temporary model downloads and temporary save files are either atomically
  promoted or safely removable; partially written files are never treated as
  valid state.

## Accessibility and keyboard contract

- Every visible primary action has an accessible name describing the current
  action, not a combined or stale state.
- Tool selection is exposed as checked state, never by disabling the active
  tool.
- Tab and Shift+Tab traverse only visible controls in visual order.
- Canvas focus is restored after class acceptance, time acceptance/cancel,
  assist acceptance/rejection, and file selection.
- Essential actions remain reachable without toolbar-overflow controls.
- User-facing shortcuts use native platform text while stored shortcut strings
  remain portable.

## Compatibility and migration

- Pascal VOC, YOLO, YOLO segmentation, CreateML, COCO, and video-project data
  formats do not change.
- Undo/redo command semantics remain intact; autosave persists the resulting
  model state but does not clear history.
- Existing predefined classes and session label history seed Active class.
- Existing `singleclass` users migrate to `reuse_active`.
- Existing navigation-autosave users migrate to automatic continuous saving.
- PyQt4 import fallbacks remain in touched production modules.
- No new mandatory AI or video dependency is added to the base installation.

## Verification plan

### Automated contracts

1. Workflow tests prove first-class confirmation, repeated prompt-free commits,
   persistent Rectangle/Polygon across navigation, explicit Select, Escape, and
   exactly one checked tool.
2. Save-coordinator tests prove 250 ms coalescing, mutation-during-save replay,
   revision-safe completion, forced image-navigation flush, video snapshot
   saving, Retry, and close failure handling.
3. View tests prove initial deferred Fit Window, checked-action agreement,
   fit recalculation after image navigation, manual zoom preservation, and
   video-frame transform preservation.
4. Responsive tests render at 800×600, 960×640, 1366×768, and 1440×900 and
   assert that canvas, transport, time, speed, seek, save state, and inspector
   affordance remain visible and non-overlapping.
5. Timeline tests prove mouse, keyboard, and accessibility seeking; final drag
   emission; validator behavior; Return/Escape focus; semantic Play/Pause; end
   pause; VFR neighboring PTS; and compact Track-menu behavior.
6. Assist tests prove explicit setup, no automatic download, progress, true
   cancellation without retry, atomic cache promotion, failure recovery,
   provisional preview, accept/reject, active-class resolution, autosave, and
   optional video tracking.
7. Recovery tests open, replace, fail, cancel, close, and reopen documents while
   stale async completions are delivered, proving the current generation wins.
8. Focused suites and the complete base and video-enabled suites pass.

### Live macOS matrix

Use the supplied unique videos:

- `000414_000480_2025_09_04_17-49-10_w.mp4`
- `000414_000480_2025_09_04_17-06-31_w.mp4`
- `000414_000558_2025_10_13_08-15-48_w.mp4`

For each video: open, inspect full-frame fitting, step forward/backward, play,
pause, mouse-seek, keyboard-seek, accessibility-seek, enter valid and invalid
time, annotate twice with one class choice, navigate while autosaving, verify,
save/reopen, run and cancel propagation, exercise Assist setup/cancel when
available, close, and reopen. Repeat the essential flow at 800-pixel width and
repeat open/play/seek/close ten times to detect shutdown crashes.

For the four-frame image dataset: choose `vehicle` once, draw two rectangles,
navigate with `D`, confirm class/tool/fit continuity, verify immediate sidecar
creation, undo/redo across autosaves, quit, and reopen.

## Release gates

- No `Python quit unexpectedly` or abandoned-worker warning occurs in the live
  repetition matrix.
- Every supplied video passes the complete functional matrix with exact PTS
  stepping and durable annotations.
- The 800-pixel layout exposes all essential image and video actions.
- Save failure and model-download cancellation are recoverable without restart
  or data loss.
- The full automated suite, video-enabled suite, screenshot matrix, and live
  macOS matrix pass.
- Nothing is pushed automatically.

## Non-goals

- Replacing Qt or changing annotation formats.
- Adding audio playback or editing.
- Building a cloud collaboration service or model marketplace.
- Automatically propagating AI results without user intent.
- Adding every detector or segmentation model supported by competitors.
- Reworking unrelated dataset export and statistics features.
