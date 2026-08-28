"""Contracts for immutable committed-document identity values."""

import os
from pathlib import Path

from libs.core.document_identity import DocumentIdentity


def test_document_identity_normalizes_path_and_generation_for_hashing():
    """Stale callbacks compare one normalized committed-document value."""
    first = DocumentIdentity('image', Path('fixtures/../frame.png'), '3')
    equivalent = DocumentIdentity('image', './frame.png', 3)
    newer = DocumentIdentity('image', './frame.png', 4)

    assert first.kind == 'image'
    assert first.key == os.path.abspath('frame.png')
    assert first.generation == 3
    assert first == equivalent
    assert first != newer
    assert {first: 'current'}[equivalent] == 'current'


def test_document_identity_keeps_an_empty_key_for_no_committed_document():
    """The empty workspace has a stable, non-path identity key."""
    identity = DocumentIdentity('none', None, 0)

    assert identity.key == ''
    assert identity.generation == 0
