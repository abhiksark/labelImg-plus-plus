"""Deterministic PyAV media fixtures created only for video tests."""

import fractions

import pytest


@pytest.fixture
def make_video():
    av = pytest.importorskip('av')
    np = pytest.importorskip('numpy')

    def create(path, frames=12, width=96, height=64, rate=12,
               container_format=None, rotation=0):
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
