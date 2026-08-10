from libs.widgets.ultralyticsExportDialog import UltralyticsExportDialog


def test_ultralytics_export_dialog_has_export_defaults(tmp_path):
    dialog = UltralyticsExportDialog(
        image_count=10, default_dir=str(tmp_path / 'dataset'))
    try:
        assert dialog.windowTitle() == 'Export Ultralytics Dataset'
        assert dialog.run_btn.text() == 'Export'
        assert not dialog.stratified_cb.isVisible()
        assert dialog.output_dir.endswith('_ultralytics')
        assert dialog.ratios == {'train': .7, 'val': .2, 'test': .1}
        assert dialog.copy_mode is True
    finally:
        dialog.close()
