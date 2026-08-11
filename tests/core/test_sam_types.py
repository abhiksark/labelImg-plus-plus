from dataclasses import FrozenInstanceError

import pytest

from libs.core.sam_types import SamResult, normalize_sam_output_mode


def test_sam_result_is_frozen_plain_data():
    result = SamResult(
        polygon=((1.0, 2.0), (4.0, 2.0), (4.0, 8.0)),
        bounds=(1.0, 2.0, 5.0, 9.0))
    with pytest.raises(FrozenInstanceError):
        result.bounds = (0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize('value, expected', [
    ('polygon', 'polygon'), ('box', 'box'),
    ('rectangle', 'polygon'), (None, 'polygon'), (3, 'polygon'),
])
def test_output_mode_normalization(value, expected):
    assert normalize_sam_output_mode(value) == expected
