from dataclasses import FrozenInstanceError

import pytest

from libs.core.assist_state import (
    AssistFailureKind,
    AssistPhase,
    AssistPrompt,
    AssistPreview,
    AssistSnapshot,
    AssistState,
)


def test_setup_download_run_preview_accept_sequence():
    assist = AssistState()
    assist.require_setup('mobile-sam')
    assert assist.snapshot.phase is AssistPhase.SETUP_REQUIRED
    assist.ready_to_download('mobile-sam')
    assist.start_download()
    assist.download_ready()
    assist.start_run(document_generation=7)
    assist.show_preview(document_generation=7, result='preview')
    assert assist.snapshot.phase is AssistPhase.PREVIEW
    assert assist.accept_preview() == 'preview'
    assert assist.snapshot.phase is AssistPhase.READY


def test_stale_preview_cannot_replace_new_document():
    assist = AssistState()
    assist.ready()
    assist.start_run(document_generation=2)
    before = assist.snapshot
    assert not assist.show_preview(document_generation=1, result='stale')
    assert assist.snapshot == before


def test_invalid_lifecycle_transitions_raise_value_error():
    assist = AssistState()
    with pytest.raises(ValueError):
        assist.start_download()
    with pytest.raises(ValueError):
        assist.download_ready()
    with pytest.raises(ValueError):
        assist.start_run(document_generation=1)
    with pytest.raises(ValueError):
        assist.accept_preview()
    with pytest.raises(ValueError):
        assist.reject_preview()


def test_preview_review_requires_current_running_generation():
    assist = AssistState()
    assist.ready()
    assist.start_run(document_generation=4)
    assist.show_preview(document_generation=4, result='preview')
    with pytest.raises(ValueError):
        assist.show_preview(document_generation=4, result='replacement')


def test_failure_state_and_prompt_preview_records_are_immutable():
    prompt = AssistPrompt(
        mode='points', positive_points=((1.0, 2.0),),
        negative_points=((3.0, 4.0),))
    preview = AssistPreview(result='mask', prompt=prompt)
    snapshot = AssistSnapshot(preview=preview)
    with pytest.raises(FrozenInstanceError):
        prompt.mode = 'box'
    with pytest.raises(FrozenInstanceError):
        preview.result = 'other'
    with pytest.raises(FrozenInstanceError):
        snapshot.phase = AssistPhase.READY


def test_fail_records_typed_kind_and_message():
    assist = AssistState()
    assist.ready()
    assist.fail(AssistFailureKind.OFFLINE, RuntimeError('offline'))
    assert assist.snapshot.phase is AssistPhase.FAILED
    assert assist.snapshot.failure_kind is AssistFailureKind.OFFLINE
    assert assist.snapshot.message == 'offline'


def test_reject_preview_discards_result_and_returns_ready():
    assist = AssistState()
    assist.ready('mobile-sam')
    assist.start_run(document_generation=1)
    assist.show_preview(document_generation=1, result='preview')
    assert assist.reject_preview() is None
    assert assist.snapshot.phase is AssistPhase.READY
    assert assist.snapshot.preview is None
