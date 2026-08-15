# Annotation flow product contract

Status: implemented and visually verified

Scope: image and video annotation from source opening through completion

Runtime behavior: implemented by the linked workspace actions and model state

## Product promise

An annotator should always be able to answer three questions without opening a
menu or interpreting internal state:

1. What am I doing now?
2. What happens after my next gesture?
3. What remains before this item is complete?

The product optimizes for sustained annotation work. A first-time user should
be able to discover the loop from visible controls, while an experienced user
should be able to repeat it from the keyboard without focus traps or modal
interruptions.

## Original-flow diagnosis

The modern shell was visually cleaner than the legacy application, but its
behavior was still assembled from feature surfaces rather than one workflow.

- Before the persistent-tool slice, a completed rectangle returned the canvas
  to Select. Repeated boxes required `W → draw → classify → W` for every
  object.
- Class reuse was split between an always-visible “Use default label” control,
  a hidden Single Class setting, the inline picker, and remembered session
  state. The user cannot see which rule will classify the next shape.
- Before the completion slice, Save, verification, navigation, dirty state,
  and object count were separate indicators with no single completion action.
- The inspector gave permanent space to controls that were often irrelevant,
  while selected-object actions and current session behavior are weak.
- Video navigation exposed PTS and approximate frame internals instead of
  leading with elapsed time and annotation state.
- Propagation was started from the far edge of the timeline or the Tools menu,
  even though it acts on the selected track.
- A finished propagation created pending work, but pending review was surfaced
  through multiple menu actions rather than a visible queue with a clear next
  item.
- The status strip reported many facts at once but did not express the next
  product action.

These are flow defects. Changing spacing or colors alone cannot fix them.

## Interaction model

### 1. Persistent annotation session

Box, Polygon, and Smart Select remain armed until the user explicitly chooses
Select, changes tools, presses Escape while idle, navigates, or completes the
item. Confirming one shape must not silently change tools.

The inspector shows an **Annotation session** card whenever a creation tool is
active. It states both dimensions that affect the next gesture:

- geometry tool: Box, Polygon, or Smart Select;
- class strategy: Confirm each, Repeat last class, or Fixed class.

This replaces the permanent default-label checkbox/combo presentation. Existing
settings stay compatible; the session card is a clearer projection over them.

### 2. In-context class confirmation

New geometry stays provisional until its class is confirmed. The picker opens
beside the geometry and makes the fastest likely action explicit:

- Enter repeats the last class when one exists;
- recent/known classes are keyboard-navigable;
- typing filters and may create a class;
- Escape discards only the provisional geometry;
- confirmation returns focus to the canvas and retains the active creation
  tool.

The picker remains non-modal and one confirmation plus geometry remains one
undo step.

### 3. One completion action

The command bar has one visually primary action based on document state:

- image/folder item: **Done & Next**;
- completed image: **Next image**;
- video canvas: **Browse video**;
- pending video work: **Review queue**.

For an image, Done & Next performs the already-supported save, verification,
and navigation behavior as one orchestrated user action. If any part cannot be
completed, the user remains on the item and receives an actionable message.

Automatic saving is described as a durable state (“Saved automatically”), not
as an unexplained dot or a separate preference the user must remember.

### 4. Contextual object inspector

The top of the Objects/Tracks inspector is contextual, not a static form:

- creation tool active → annotation-session card;
- exact manual video anchor selected → Propagate and scoped track actions;
- pending suggestion selected → review progress and run-level action;
- no selection → concise empty guidance;
- selection → editable class, type/status, duplicate, and delete.

The object list remains the single authoritative projection. Image-only
controls do not appear in video context, and disabled actions do not occupy the
primary action position.

### 5. Video as a four-stage workflow

The video footer communicates a stable sequence:

1. Anchor
2. Propagate
3. Review
4. Export

The sequence is descriptive, not a wizard and not a new persisted mode. Users
may jump to any valid stage through existing actions and overview navigation.
The current stage follows canonical video state.

Elapsed time is the primary position language. Exact PTS remains available in
diagnostics/tooltips where it is useful, but is not the main navigation label.

### 6. Review as a queue

Review holds the frame and affected track in context and gives three visible
actions:

- Previous issue
- Reject
- Accept & Next

Shift+Enter accepts and advances; Backspace rejects and advances. The queue
prioritizes explicit pending/event frames and shows `current of total`. Run-level
accept/reject remains available in the selected-track card, with confirmation
when it affects more than the visible item.

Leaving and returning to review resumes from the current canonical pending set;
no new database state is required.

## State model

| Product state | Primary action | Inspector context | Footer context |
|---|---|---|---|
| Empty | Open source | Recent work / source guidance | None |
| Drawing | Done & Next | Annotation session | Tool + class behavior |
| Classifying | Done & Next disabled | Annotation session | Provisional, unsaved |
| Image ready | Next image | Selected object | Saved + complete |
| Video anchor | Browse video | Selected-track propagation | Anchor → Propagate |
| Propagating | Cancel | Progress for selected/all tracks | Stable progress + ETA |
| Pending review | Review queue | Pending count / run action | Propagate → Review |
| Reviewing | Accept & Next | Selected pending track | Queue position |
| Video ready | Browse video | Overview export readiness | Review → Export |

## Architecture constraints

- Reuse authoritative `QAction` objects and existing shortcut IDs.
- Do not change annotation formats, SQLite schema, plugin API, export contract,
  undo boundaries, or dirty-state semantics.
- Preserve Python 3.8–3.13 and lazy optional video/SAM imports.
- Keep widgets and shape/model mutation on the GUI thread; background workers
  continue to return plain immutable data or `QImage`.
- Preserve accepted manual anchors, pending review compatibility, generation
  fences, cancellation, and independent decoders.
- Store only bounded presentation preferences. Do not persist workflow state
  that can be derived from the current document.

## Implementation sequence

### Slice A — sustained image annotation

Status: implemented and visually verified.

- retain Box/Polygon after class confirmation;
- add the annotation-session card;
- state the next gesture near the canvas;
- keep Escape, focus restoration, undo, default-label, and single-class
  behavior compatible;
- replace the permanent default-label controls with the session projection.

Acceptance: annotate ten boxes of three classes without re-arming Box, touching
a menu, or losing canvas shortcuts.

### Slice B — completion and navigation

Status: implemented and visually verified.

- add state-derived command-bar primary action;
- orchestrate save + verify + next using existing request paths;
- make automatic save state explicit;
- provide recoverable failures without navigation.

Acceptance: process a mixed annotated/unannotated directory using canvas,
picker, and one completion key only.

### Slice C — contextual inspector

Status: implemented and visually verified.

- introduce selected-object property/action surface;
- show creation, anchor, propagation, and review cards based on state;
- remove image-only controls from video context;
- preserve model/view identity and visibility behavior.

Acceptance: every enabled track mutation reachable from the selected track
without opening Tools.

### Slice D — video workflow footer

Status: implemented and visually verified.

- replace internal-first timeline copy with elapsed-time-first copy;
- project Anchor/Propagate/Review/Export stages;
- keep exact seek, VFR PTS correctness, marker painting, and propagation
  cancellation intact.

Acceptance: a new user can create an anchor and find propagation without a
tooltip, shortcut reference, or menu.

### Slice E — review queue

Status: implemented and visually verified.

- derive the queue from pending observations and event frames;
- add Previous issue, Reject, Accept & Next;
- synchronize canvas, selected track, timeline, overview, and counts;
- retain run-level actions with explicit scope.

Acceptance: review a propagation run from the keyboard with no focus change and
no disagreement among pending counts.

### Slice F — overview-to-export completion

Status: implemented and visually verified.

- make Browse video the stable entry to lanes/frames;
- surface review/export readiness in the overview;
- align the final export decision with the frames displayed by the overview;
- treat thumbnail decoding and distinct export as their separately scoped
  implementation work.

Acceptance: the user can explain what will be exported before opening the
export dialog, and preview/export counts agree.

## Verification gates for every runtime slice

- workflow-level Qt tests, not widget existence alone;
- action identity and shortcut reachability;
- focus behavior after mouse and keyboard interactions;
- undo/redo and dirty-state checks;
- read-only and in-flight-worker states;
- light/dark and 1×/2× screenshots at 1366×768 and 1440×900;
- Python 3.8 AST, Ruff, compileall, resources, lazy optional imports;
- focused tests followed by the full base and relevant optional suites.
