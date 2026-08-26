"""Recovery contracts for transactional document replacement."""

import os
import time
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import get_main_app
from libs.core.assist_state import AssistFailureKind, AssistPhase
from libs.core.continuous_save import SaveTicket
from libs.core.document_identity import DocumentIdentity
from libs.core.save_pipeline import SaveRequest
from libs.core.video_types import DocumentKind
from libs.widgets.inlineErrorBanner import InlineErrorBanner


app = QApplication.instance() or QApplication([])


def _wait(application, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _image(path, color=Qt.white):
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path))


def test_inline_open_error_banner_exposes_recovery_actions_accessibly():
    """Replacement failure offers one visible keyboard-accessible recovery path."""
    banner = InlineErrorBanner()
    retry = QSignalSpy(banner.retryRequested)
    choose = QSignalSpy(banner.chooseAnotherRequested)
    banner.show_error('Could not open frame.png')
    banner.show()
    QApplication.processEvents()
    try:
        assert banner.isVisible()
        assert banner.message.text() == 'Could not open frame.png'
        assert banner.retry_button.text() == 'Retry'
        assert banner.choose_button.text() == 'Choose another file'
        for button in (banner.retry_button, banner.choose_button):
            assert button.accessibleName().strip()
            assert button.width() >= 32
            assert button.height() >= 32
        banner.retry_button.click()
        banner.choose_button.click()
        assert len(retry) == 1
        assert len(choose) == 1
    finally:
        banner.close()


def test_failed_image_replacement_keeps_committed_workspace_and_identity(
        tmp_path):
    """A failed candidate image must not replace or disable the live document."""
    application, window = get_main_app()
    current = tmp_path / 'current.png'
    _image(current)
    assert window.load_file(str(current))
    try:
        before_identity = window.document_identity
        before_pixmap = window.canvas.pixmap.cacheKey()
        assert window.actions.create.isEnabled()

        window.request_open_file(str(tmp_path / 'missing.png'),
                                 skip_prompt=True)
        assert _wait(
            application,
            lambda: not window.task_coordinator.queue_depths()['interactive'])

        assert window.document_identity == before_identity
        assert window.canvas.pixmap.cacheKey() == before_pixmap
        assert window.canvas.isEnabled()
        assert window.actions.create.isEnabled()
        assert window.inline_open_error.isVisible()
        assert window.inline_open_error.retry_button.text() == 'Retry'
    finally:
        window.dirty = False
        window.close()


def test_stale_assist_failure_for_a_previous_same_generation_image_is_ignored(
        tmp_path):
    """Assist callbacks carry document identity, not only dataset generation."""
    _application, window = get_main_app()
    first = tmp_path / 'first.png'
    second = tmp_path / 'second.png'
    _image(first)
    _image(second)
    assert window.load_file(str(first))
    try:
        window.assist_state.ready('mobile-sam')
        window._assist_document_identity = window.document_identity
        window.assist_state.start_run(window._dataset_generation)
        generation = window._dataset_generation

        assert window.load_file(str(second))
        window._on_assist_preview_failed(
            generation, AssistFailureKind.INFERENCE, 'old image failed')

        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert window.document_identity.key == os.path.abspath(str(second))
    finally:
        window.dirty = False
        window.close()


def test_old_same_path_save_completion_cannot_clean_newer_identity_epoch(
        tmp_path):
    """A reload changes the save identity even when path and generation match."""
    _application, window = get_main_app()
    image_path = tmp_path / 'same.png'
    _image(image_path)
    assert window.load_file(str(image_path))
    try:
        window.set_dirty()
        ticket = SaveTicket(
            window._continuous_document_key(), window._dataset_generation,
            window._document_revision)
        request = SaveRequest(
            image_path=str(image_path), annotation_path=str(tmp_path / 'same.xml'),
            label_file_format=window.label_file_format, shapes=(),
            class_list=(), verified=False, revision=ticket.revision)

        assert window.load_file(str(image_path))
        window.dirty = True
        window._on_save_result(
            request.annotation_path, request, None, ticket.generation, ticket)

        assert window.dirty is True
    finally:
        window.dirty = False
        window.close()


def test_video_replacement_error_keeps_committed_image_and_projects_retry(
        tmp_path):
    """A video candidate failure never clears the working image workspace."""
    _application, window = get_main_app()
    image_path = tmp_path / 'current.png'
    _image(image_path)
    assert window.load_file(str(image_path))
    try:
        before = window.document_identity
        pixmap_key = window.canvas.pixmap.cacheKey()
        window._on_video_open_error(
            'unreadable project', window._video_open_request_id,
            window._dataset_generation, str(tmp_path / 'bad.mp4'))

        assert window.document_identity == before
        assert window.canvas.pixmap.cacheKey() == pixmap_key
        assert window.canvas.isEnabled()
        assert window.inline_open_error.isVisible()
        assert 'unreadable project' in window.inline_open_error.message.text()
    finally:
        window.dirty = False
        window.close()


def test_inline_retry_replays_the_exact_failed_image_candidate(tmp_path):
    """Retry retains the candidate snapshot instead of reopening the live file."""
    application, window = get_main_app()
    current = tmp_path / 'current.png'
    missing = tmp_path / 'missing.png'
    _image(current)
    assert window.load_file(str(current))
    try:
        before_snapshot = window.dataset_snapshot
        window.request_open_file(str(missing), skip_prompt=True)
        assert _wait(
            application,
            lambda: not window.task_coordinator.queue_depths()['interactive'])
        with patch.object(window, 'request_load_file') as retry:
            window.inline_open_error.retry_button.click()

        retry.assert_called_once()
        args, kwargs = retry.call_args
        assert args == (str(missing),)
        assert kwargs['skip_prompt'] is True
        assert kwargs['replacement_snapshot'].image_paths == (str(missing),)
        assert kwargs['previous_snapshot'] is before_snapshot
    finally:
        window.dirty = False
        window.close()


def test_stale_decode_identity_cannot_reach_the_frame_mutation_boundary(
        tmp_path):
    """A same-generation decoder callback is rejected before painting a frame."""
    _application, window = get_main_app()
    source = tmp_path / 'current.mp4'
    source.write_bytes(b'placeholder')
    try:
        window._set_document_kind(DocumentKind.VIDEO)
        window.video_snapshot = SimpleNamespace(
            source_path=str(source), project_path=None, fingerprint='current')
        window._video_frame_request_id = 7
        stale = DocumentIdentity(
            'video', str(tmp_path / 'old.mp4'), window._dataset_generation)
        result = SimpleNamespace(
            frame_ref=SimpleNamespace(fingerprint='current'))
        with patch.object(window, '_commit_video_frame') as commit:
            window._on_video_frame_result(
                result, 7, window._dataset_generation, identity=stale)

        commit.assert_not_called()
    finally:
        window.video_snapshot = None
        window.dirty = False
        window.close()
