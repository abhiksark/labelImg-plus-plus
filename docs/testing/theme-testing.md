# Dark Theme Testing Guide

## Automated Tests

Run all theme tests:
```bash
python3 -m pytest tests/ -k theme -v
```

## Manual Testing Checklist

### Basic Theme Toggle
- [ ] Ctrl+D toggles between light and dark
- [ ] View → Dark Mode menu item works
- [ ] Theme persists after restart

### Component Visual Tests

#### Main Window
- [ ] Background color changes
- [ ] Text is readable in both themes
- [ ] Borders are visible

#### Canvas
- [ ] Background matches theme
- [ ] Verified overlay tint appropriate for theme
- [ ] Shapes are visible in both themes

#### Gallery
- [ ] Placeholder images match theme
- [ ] Item backgrounds match theme
- [ ] Status borders (gray/blue/green) visible in both themes
- [ ] Preset buttons (S/M/L/XL) have correct backgrounds
- [ ] Slider controls match theme

#### Dialogs
- [ ] Label dialog text readable
- [ ] Label checker issue colors appropriate for theme

#### Status Bar
- [ ] Save status dot (green/orange) appropriate for theme

### Edge Cases
- [ ] Theme switch while gallery open
- [ ] Theme switch with image loaded
- [ ] Theme switch with dialogs open
