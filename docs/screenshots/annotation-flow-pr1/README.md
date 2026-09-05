# Annotation flow PR 1 visual artifacts

These screenshots exercise the runtime Qt workspace, not the browser
prototype. Each state is retained at 1366x768 in light mode and 1440x900 in
dark mode, at both 1x and 2x logical scaling.

- `fit-*`: a newly opened 1600x1000 image is fully visible in Fit Window with
  the canvas at the scroll viewport origin.
- `review-*`: entering a pending video suggestion has switched the active tool
  to Select while keeping the pending track selected.
- `save-error-*`: a failed completion save keeps the verified geometry and
  current image visible, shows the persistent recovery notice, and projects
  `Retry save & next` into the command bar.

The `*-contact-sheet.png` files collect the four theme/scale variants for
side-by-side review.
