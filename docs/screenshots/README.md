# Screenshots

## Workspace 3.2

`workspace-3.2-balanced/` contains the accepted browser-lab contract for the
Balanced workspace at 1366x768 and 1440x900. Dense and Canvas-first remain
archived comparison studies in the interactive prototype and are not runtime
themes.

`workspace-3.2-tool-rail/` contains fixed Linux/offscreen Qt captures of the
first runtime slice in light and dark mode at both approval sizes. The legacy
docks are intentionally still present in this slice; the fixed-inspector PR
replaces them next.

`workspace-3.2-fixed-inspector/` contains fixed Linux/offscreen Qt captures of
the Objects/Files inspector in light, dark, and collapsed states at 1366x768
and 1440x900. The existing annotation and file projections are reparented into
the fixed panel; the collapsed captures retain the accessible reopen control
at the right edge of the canvas.

`workspace-3.2-unified-inspector/` contains fixed Linux/offscreen Qt captures
of the unified searchable object projection in light and dark mode at both
approval sizes. Rectangle and polygon rows share one list, with no nested
annotation tabs; video tests separately cover track rows that are absent from
the current frame.

`workspace-3.2-final/` is the final Balanced workspace acceptance matrix. It
contains Empty, Image, embedded Gallery, Video, collapsed-inspector,
read-only/disabled, dark-mode, and true 2x-DPI image states at 1366x768 and
1440x900. The matrix verifies that the rail, command bar, inspector, compact
canvas controls, integrated timeline, and slim status strip remain in the
single main window with no docks or detached gallery.

## Workspace 3.3

`workspace-3.3-inline-picker/` contains fixed Linux Qt captures of the
provisional geometry and non-modal class picker in light and dark mode. The
1x captures use the 1366x768 and 1440x900 approval sizes; the matching HiDPI
captures retain those logical sizes and are stored at 2732x1536 and 2880x1800
physical pixels. The empty Objects projection demonstrates that provisional
geometry is not canonical until class confirmation.

This directory contains screenshots demonstrating various features of labelImg++.

## Required Screenshots

### Dark Mode Feature

#### `light-mode.png`
**Description:** Main application window in light theme showing:
- Main toolbar with icons on the left
- Image canvas in the center with sample annotations
- Label list panel on the right
- Gallery thumbnails at the bottom (if visible)
- Status bar at the bottom
- At least 2-3 bounding boxes with labels visible

**How to capture:**
1. Launch labelImgPlusPlus
2. Open a sample image with annotations
3. Ensure View > Dark Mode is unchecked (light theme active)
4. Take a full window screenshot
5. Save as `light-mode.png` (PNG format, recommended size: 1920x1080 or similar)

#### `dark-mode.png`
**Description:** Main application window in dark theme showing:
- Same view as light-mode.png but with dark theme active
- Main toolbar with dark background
- Dark gray canvas background
- Dark-themed panels and controls
- Same annotations visible for comparison
- Status bar in dark theme

**How to capture:**
1. With the same image and annotations as light-mode screenshot
2. Press Ctrl+Shift+T or select View > Dark Mode to enable dark theme
3. Take a full window screenshot
4. Save as `dark-mode.png` (PNG format, recommended size: 1920x1080 or similar)

## Screenshot Guidelines

- **Resolution:** Use the feature's fixed review matrix when specified;
  otherwise prefer 1920x1080 or higher for documentation
- **Format:** PNG (lossless) preferred
- **Content:** Show meaningful sample images with multiple bounding boxes
- **Annotations:** Use diverse labels (e.g., "person", "car", "dog") to demonstrate the feature
- **Window State:** Full window capture, not cropped
- **Clean State:** No error messages or temporary UI elements
- **Consistency:** Use the same sample image for light/dark comparison

## Adding More Screenshots

When adding new feature screenshots:
1. Create descriptive filename (e.g., `gallery-mode.png`, `label-dialog.png`)
2. Add entry to this README with description and capture instructions
3. Reference in relevant documentation markdown files
4. Use consistent resolution and quality

## Workspace 3.2 command-bar review

The `workspace-3.2-command-bar/` directory contains the fixed Linux visual
review set for the first modern-workspace slice. Each empty, image, gallery,
video, and disabled-action state is captured at both 1366×768 and 1440×900 at
96 DPI. Review the set for:

- a single 44 px application row below the native OS title bar;
- no native File/Edit/View menu row;
- visible application, Open, document, navigation, Save, Verify, format, and
  overflow controls without clipping;
- consistent document names, positions, and disabled action styling; and
- unchanged canvas, annotation, gallery, and video behavior below the row.

High-DPI full-window review joins the next 3.2 slice: the legacy text-under-icon
toolbar still sets a window minimum taller than 768 px at 2× scaling and is the
component that slice replaces. Collapsed-inspector review begins with the fixed
inspector slice.

## Alternative: Placeholder Images

Until actual screenshots are captured, the documentation uses placeholder references. The application is fully functional, and users can see the actual themes by using the feature.
