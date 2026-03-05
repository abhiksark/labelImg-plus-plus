History
=======

2.2.0 (2026-03-05)
------------------

* Add Clear Recent Files option to File > Open Recent menu (#14)
* Add Review Lock: prevent editing verified images via View > Lock on Verify (#22)
* Add Batch Verify/Unverify dialog under Tools menu (#22)
* Add status filter (All/Annotated/Verified/Unannotated) to file list (#22)
* Add Snap to Grid overlay with configurable grid size (8/16/32/64px) (#18)
* Add Edge Alignment mode with visual guide lines (#18)
* Add customizable keyboard shortcuts with full editor dialog (#8)
* Add shortcut export/import as JSON files (#8)
* Add Dataset Splitting tool with train/val/test ratios (#21)
* Add stratified split option for balanced class distribution (#21)
* Add split manifest JSON generation for reproducibility (#21)


2.1.1 (2026-02-05)
------------------

* Rename command from ``labelImgPlusPlus`` to ``labelimgpp`` and ``labelimgplusplus``
* Add deprecation warning for old ``labelImgPlusPlus`` command (still works for backwards compatibility)
* Update all documentation to reference new command names


2.1.0b (2026-02-05)
-------------------

* Add Dark Mode theme support with Ctrl+Shift+T toggle (Beta Release)
* Add 13 new theme-aware color keys to Settings
* Fix hardcoded colors in canvas, gallery widget, and dialogs
* Add hex_to_qcolor() utility function for color handling
* Add comprehensive theme documentation (docs/features/dark-mode.md)
* Add theme integration tests (tests/test_theme.py)
* Fix keyboard shortcut conflicts
* Improve gallery widget styling for both light and dark themes


2.0.1 (2025-01-22)
------------------

* Update all references to labelImgPlusPlus
* Add PyPI and CI badges to README
* Update build-tools for labelImgPlusPlus
* Update Chinese and Japanese translations
* Add comprehensive developer documentation


2.0.0 (2025-01-22)
------------------

* Rebrand to labelImg++
* Add Gallery Mode - full-screen thumbnail browser with Ctrl+G
* Thumbnails show annotation status (gray/blue/green borders)
* Adjustable thumbnail size slider (40px - 300px)
* Modernize packaging with pyproject.toml
* Add GitHub Actions CI/CD with PyPI trusted publishing
* Update dependencies to latest versions


1.8.6 (2021-10-10)
------------------

* Display box width and height


1.8.5 (2021-04-11)
------------------

* Merged a couple of PRs
* Fixed issues
* Support CreateML format


1.8.4 (2020-11-04)
------------------

* Merged a couple of PRs
* Fixed issues

1.8.2 (2018-12-02)
------------------

* Fix pip depolyment issue


1.8.1 (2018-12-02)
------------------

* Fix issues
* Support zh-Tw strings


1.8.0 (2018-10-21)
------------------

* Support drawing sqaure rect
* Add item single click slot
* Fix issues

1.7.0 (2018-05-18)
------------------

* Support YOLO
* Fix minor issues


1.6.1 (2018-04-17)
------------------

* Fix issue

1.6.0 (2018-01-29)
------------------

* Add more pre-defined labels
* Show cursor pose in status bar
* Fix minor issues

1.5.2 (2017-10-24)
------------------

* Assign different colors to different lablels

1.5.1 (2017-9-27)
------------------

* Show a autosaving dialog

1.5.0 (2017-9-14)
------------------

* Fix the issues
* Add feature: Draw a box easier


1.4.3 (2017-08-09)
------------------

* Refactor setting
* Fix the issues


1.4.0 (2017-07-07)
------------------

* Add feature: auto saving
* Add feature: single class mode
* Fix the issues

1.3.4 (2017-07-07)
------------------

* Fix issues and improve zoom-in

1.3.3 (2017-05-31)
------------------

* Fix issues

1.3.2 (2017-05-18)
------------------

* Fix issues


1.3.1 (2017-05-11)
------------------

* Fix issues

1.3.0 (2017-04-22)
------------------

* Fix issues
* Add difficult tag
* Create new files for pypi

1.2.3 (2017-04-22)
------------------

* Fix issues

1.2.2 (2017-01-09)
------------------

* Fix issues
