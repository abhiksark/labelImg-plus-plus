# Workspace 3.2 browser lab

This dependency-free prototype explores the complete modern workspace before
the remaining Qt slices are implemented. It does not import application code
or alter runtime behavior.

Open `index.html` in a browser and compare:

- **A · Balanced** — accepted implementation target, with a fixed 52 px tool
  rail and 304 px inspector;
- **B · Dense** — archived comparison study; and
- **C · Canvas-first** — archived comparison study.

Each direction supports Empty, Image, Gallery, and Video states. The tool rail
and inspector collapse control are interactive.

Chrome capture examples:

```bash
google-chrome --headless --disable-gpu --hide-scrollbars \
  --window-size=1366,768 --screenshot=/tmp/workspace-lab.png \
  "file://$PWD/docs/prototypes/workspace-3.2/index.html"
```

The prototype is intentionally a design artifact. Balanced is the only runtime
workspace direction; Dense and Canvas-first are retained solely to document the
comparison that led to that decision. Approved decisions must be translated
into Qt widgets while preserving the implementation plan's action, settings,
annotation, plugin, and GUI-thread contracts.

The accepted fixed-size captures live in
`docs/screenshots/workspace-3.2-balanced/`. They cover Empty, Image, Gallery,
and Video at 1366x768 and 1440x900 with the review controls hidden.
