# Seamless annotation-flow lab

This dependency-free browser lab defines the next product contract for the
annotation loop. It is intentionally a workflow prototype rather than a theme
or a collection of isolated controls.

The five review states follow one continuous job:

1. **Draw** — choose a tool once and create several objects without re-arming it.
2. **Classify** — confirm a class beside the new geometry with the last class,
   recent classes, and keyboard behavior visible.
3. **Complete** — understand save state, finish the current item, and move to
   the next item through one primary action.
4. **Propagate** — create a manual video anchor, choose scope, and run tracking
   from the selected object rather than from a distant menu.
5. **Review** — accept or reject pending suggestions as a queue, with the frame
   and affected track held in context.

Open `index.html` directly, or capture a deterministic state with a query:

```bash
google-chrome --headless --disable-gpu --hide-scrollbars \
  --window-size=1366,768 \
  --screenshot=/tmp/annotation-flow.png \
  "file://$PWD/docs/prototypes/annotation-flow/index.html?state=draw&review=hidden"
```

Supported `state` values are `draw`, `classify`, `complete`, `propagate`, and
`review`. The prototype does not change runtime behavior. Runtime work must
continue to project the application's existing `QAction` instances, preserve
file and plugin contracts, keep video/model mutation on the GUI thread, and
retain the current undo boundaries.
