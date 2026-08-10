"""Deterministic PyAV media fixtures created only for video tests."""

import fractions

import pytest


@pytest.fixture
def make_video():
    av = pytest.importorskip('av')
    np = pytest.importorskip('numpy')

    def create(path, frames=12, width=96, height=64, rate=12,
               container_format=None, rotation=0,
               tracking_stress=False, scene_cut_at=None):
        output = av.open(str(path), mode='w', format=container_format)
        stream = output.add_stream('mpeg4', rate=rate)
        stream.width = width
        stream.height = height
        stream.pix_fmt = 'yuv420p'
        stream.gop_size = 6
        if rotation:
            stream.metadata['rotate'] = str(rotation)
        for index in range(frames):
            array = np.zeros((height, width, 3), dtype=np.uint8)
            array[:, :, 0] = (index * 17) % 255
            if tracking_stress:
                array[:, :, 0] = 0
            if scene_cut_at is not None and index >= scene_cut_at:
                array[:] = 255
            if tracking_stress:
                x0, y0 = 16 + index, 14
                array[y0:y0 + 36, x0:x0 + 36] = 35
                for y in range(y0 + 3, y0 + 34, 6):
                    for x in range(x0 + 3, x0 + 34, 6):
                        array[y - 1:y + 2, x - 1:x + 2] = \
                            (240, 240, 240)
            else:
                array[12:36, 8 + index:32 + index, 1] = 255
            frame = av.VideoFrame.from_ndarray(array, format='rgb24')
            frame.pts = index
            frame.time_base = fractions.Fraction(1, rate)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
        output.close()
        return str(path)

    return create
