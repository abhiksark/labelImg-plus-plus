# tests/widgets/test_video_frames_view.py
"""The frames grid shows exactly the frames the engine selected."""
import os
import sys
import unittest
from unittest.mock import patch

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication

from libs.core.video_model import VideoModelState
from libs.core.video_types import ObservationRecord, TrackRecord
from libs.utils import dpi
from libs.utils.styles import Theme
from libs.widgets.videoFramesView import VideoFramesView

app = QApplication.instance() or QApplication(sys.argv)


def _state():
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),)
    observations = tuple(
        ObservationRecord(track_id='t1', pts=pts, geometry=[pts, 0, pts + 10, 10],
                          review_state='pending' if pts == 30 else 'accepted')
        for pts in (0, 10, 20, 30))
    return VideoModelState(tracks, observations, (), ('car',))


def _two_track_state():
    """Two tracks sharing pts 20, so narrowing and de-duplication show up.

    t1 is annotated at 0, 10, 20, 30 and t2 at 20, 40: five distinct annotated
    pts across six observation rows.
    """
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),
              TrackRecord(track_id='t2', label='person',
                          shape_type='rectangle', color=(0, 255, 0)))
    observations = tuple(
        ObservationRecord(track_id='t1', pts=pts, geometry=[0, 0, 10, 10])
        for pts in (0, 10, 20, 30)) + tuple(
        ObservationRecord(track_id='t2', pts=pts, geometry=[5, 5, 15, 15])
        for pts in (20, 40))
    return VideoModelState(tracks, observations, (), ('car', 'person'))


class TestVideoFramesView(unittest.TestCase):

    def setUp(self):
        self.view = VideoFramesView()
        self.view.set_state(_state(), distinct_pts=(0, 20))

    def test_distinct_filter_shows_only_distinct_frames(self):
        self.view.set_filter('distinct')
        self.assertEqual(self.view.visible_pts(), [0, 20])

    def test_annotated_filter_shows_every_annotated_frame(self):
        self.view.set_filter('annotated')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30])

    def test_pending_filter_shows_only_pending(self):
        self.view.set_filter('pending')
        self.assertEqual(self.view.visible_pts(), [30])

    def test_count_changed_reports_shown_and_total(self):
        received = []
        self.view.countChanged.connect(
            lambda shown, total: received.append((shown, total)))
        self.view.set_filter('distinct')
        self.assertEqual(received[-1], (2, 4))

    def test_activating_a_tile_emits_its_pts(self):
        received = []
        self.view.frameActivated.connect(received.append)
        self.view.activate_pts(20)
        self.assertEqual(received, [20])

    def test_track_filter_narrows_to_one_track(self):
        self.view.set_filter('annotated')
        self.view.set_track_filter('t1')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30])
        self.view.set_track_filter('missing')
        self.assertEqual(self.view.visible_pts(), [])

    def test_track_filter_is_readable(self):
        """Task 7 reads this back to keep both views in step."""
        self.assertIsNone(self.view.track_filter())
        self.view.set_track_filter('t1')
        self.assertEqual(self.view.track_filter(), 't1')
        self.view.set_track_filter(None)
        self.assertIsNone(self.view.track_filter())


class TestFilterSemantics(unittest.TestCase):
    """Each filter must select a different set, or the chips are decoration."""

    def setUp(self):
        self.view = VideoFramesView()

    def test_distinct_is_the_engine_list_not_every_annotated_frame(self):
        """Swap 'distinct' and 'annotated' and this fails both ways."""
        self.view.set_state(_state(), distinct_pts=(10,))
        self.view.set_filter('distinct')
        self.assertEqual(self.view.visible_pts(), [10])
        self.view.set_filter('annotated')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30])

    def test_pending_is_read_from_the_review_state(self):
        """Not "the last frame": the pending frame sits mid-sequence here."""
        tracks = (TrackRecord(track_id='t1', label='car',
                              shape_type='rectangle', color=(255, 0, 0)),)
        observations = tuple(
            ObservationRecord(track_id='t1', pts=pts, geometry=[0, 0, 1, 1],
                              review_state='pending' if pts == 10 else
                              'accepted')
            for pts in (0, 10, 20))
        self.view.set_state(VideoModelState(tracks, observations, (), ('car',)),
                            distinct_pts=(0, 20))
        self.view.set_filter('pending')
        self.assertEqual(self.view.visible_pts(), [10])

    def test_rejected_frames_are_not_pending(self):
        """'rejected' is a third schema-enforced state, not a near-synonym.

        video_project.py constrains review_state to accepted/pending/rejected,
        so reading pending as "anything not accepted" would file frames the
        user has already thrown out under the chip that means "still needs a
        human" -- the one thing that chip must never say.
        """
        tracks = (TrackRecord(track_id='t1', label='car',
                              shape_type='rectangle', color=(255, 0, 0)),)
        observations = (
            ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 1, 1],
                              review_state='accepted'),
            ObservationRecord(track_id='t1', pts=10, geometry=[0, 0, 1, 1],
                              review_state='rejected'),
            ObservationRecord(track_id='t1', pts=20, geometry=[0, 0, 1, 1],
                              review_state='pending'),
        )
        self.view.set_state(
            VideoModelState(tracks, observations, (), ('car',)),
            distinct_pts=(0,))
        self.view.set_filter('pending')
        self.assertEqual(self.view.visible_pts(), [20])
        # A rejected frame is still an annotated frame, so it stays here.
        self.view.set_filter('annotated')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20])

    def test_a_rejected_track_is_not_pending_under_a_track_filter(self):
        """The narrowed path reads the same review_state as the wide one."""
        tracks = (TrackRecord(track_id='t1', label='car',
                              shape_type='rectangle', color=(255, 0, 0)),)
        observations = (
            ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 1, 1],
                              review_state='rejected'),
        )
        self.view.set_state(
            VideoModelState(tracks, observations, (), ('car',)),
            distinct_pts=(0,))
        self.view.set_filter('pending')
        self.view.set_track_filter('t1')
        self.assertEqual(self.view.visible_pts(), [])

    def test_a_distinct_pts_with_no_annotation_is_not_shown(self):
        """A stale engine pts is not an annotated frame, so it gets no tile."""
        self.view.set_state(_state(), distinct_pts=(0, 20, 999))
        self.assertEqual(self.view.visible_pts(), [0, 20])
        self.assertEqual(self.view.tile_count(), 2)

    def test_visible_pts_is_sorted_and_deduplicated(self):
        """Unsorted input and a shared pts must still read left to right once."""
        self.view.set_state(_two_track_state(), distinct_pts=(40, 20, 0))
        self.assertEqual(self.view.visible_pts(), [0, 20, 40])
        self.view.set_filter('annotated')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30, 40])

    def test_distinct_defaults_to_the_active_filter(self):
        """The grid opens on the frames that differ; that is its whole point."""
        self.assertEqual(self.view.filter_name(), 'distinct')
        self.view.set_state(_state(), distinct_pts=(0, 20))
        self.assertEqual(self.view.visible_pts(), [0, 20])

    def test_an_empty_state_shows_nothing(self):
        self.view.set_state(VideoModelState((), (), (), ()), distinct_pts=())
        self.assertEqual(self.view.visible_pts(), [])


class TestTrackFilter(unittest.TestCase):
    """Narrowing must actually drop the other track's frames."""

    def setUp(self):
        self.view = VideoFramesView()
        self.view.set_state(_two_track_state(), distinct_pts=(0, 20, 40))

    def test_narrowing_drops_the_other_tracks_frames(self):
        """Ignore set_track_filter and 40 survives; this is the real check."""
        self.view.set_filter('annotated')
        self.view.set_track_filter('t1')
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30])
        self.view.set_track_filter('t2')
        self.assertEqual(self.view.visible_pts(), [20, 40])

    def test_narrowing_applies_to_the_distinct_filter_too(self):
        self.view.set_filter('distinct')
        self.assertEqual(self.view.visible_pts(), [0, 20, 40])
        self.view.set_track_filter('t2')
        self.assertEqual(self.view.visible_pts(), [20, 40])

    def test_clearing_the_filter_restores_every_track(self):
        self.view.set_filter('annotated')
        self.view.set_track_filter('t2')
        self.view.set_track_filter(None)
        self.assertEqual(self.view.visible_pts(), [0, 10, 20, 30, 40])

    def test_a_track_missing_from_the_new_state_stops_filtering(self):
        """A stale id would otherwise leave the grid permanently empty."""
        self.view.set_track_filter('t2')
        self.view.set_state(_state(), distinct_pts=(0, 20))
        self.assertIsNone(self.view.track_filter())
        self.assertEqual(self.view.visible_pts(), [0, 20])


class TestCountChanged(unittest.TestCase):

    def setUp(self):
        self.view = VideoFramesView()
        self.received = []
        self.view.countChanged.connect(
            lambda shown, total: self.received.append((shown, total)))

    def test_set_state_reports_the_new_counts(self):
        self.view.set_state(_two_track_state(), distinct_pts=(0, 20))
        self.assertEqual(self.received[-1], (2, 5))

    def test_total_counts_distinct_pts_not_observation_rows(self):
        """Six observations sit on five pts; the total is frames, not rows."""
        self.view.set_state(_two_track_state(), distinct_pts=())
        self.assertEqual(self.received[-1][1], 5)

    def test_set_track_filter_reports_the_narrowed_count(self):
        self.view.set_state(_two_track_state(), distinct_pts=(0, 20, 40))
        self.view.set_filter('annotated')
        self.view.set_track_filter('t2')
        self.assertEqual(self.received[-1], (2, 5))

    def test_shown_never_exceeds_the_total(self):
        """"1 of 0" is nonsense from a widget whose job is legible counts."""
        self.view.set_state(VideoModelState((), (), (), ()), distinct_pts=(5,))
        self.assertEqual(self.received[-1], (0, 0))

    def test_a_stale_distinct_pts_is_not_counted_as_shown(self):
        self.view.set_state(_state(), distinct_pts=(0, 20, 999))
        shown, total = self.received[-1]
        self.assertEqual((shown, total), (2, 4))
        self.assertLessEqual(shown, total)

    def test_the_total_is_never_narrowed_by_the_track_filter(self):
        """"2 of 5" is the redundancy story; "2 of 2" tells the user nothing."""
        self.view.set_state(_two_track_state(), distinct_pts=(0, 20, 40))
        self.view.set_track_filter('missing')
        self.assertEqual(self.received[-1], (0, 5))


class TestGridRendering(unittest.TestCase):
    """visible_pts() must describe the tiles, not a parallel computation."""

    def setUp(self):
        self.view = VideoFramesView()
        self.view.set_state(_state(), distinct_pts=(0, 20))

    def test_one_tile_per_visible_frame(self):
        self.view.set_filter('annotated')
        self.assertEqual(self.view.tile_count(), 4)
        self.view.set_filter('distinct')
        self.assertEqual(self.view.tile_count(), 2)

    def test_tiles_are_captioned_with_their_pts(self):
        self.view.set_media_context('clip', 0, 1, 10, 96, 64)
        self.view.set_filter('annotated')
        self.assertEqual(self.view.tile_captions(),
                         ['00:00.000', '00:01.000',
                          '00:02.000', '00:03.000'])
        self.assertIn(
            'Exact PTS 30', self.view.list_widget.item(3).toolTip())

    def test_thumbnail_cache_is_bounded_and_pending_overlay_is_painted(self):
        self.view.set_media_context('clip', 0, 1, 10, 96, 64)
        image = QImage(96, 64, QImage.Format_RGB32)
        image.fill(QColor('#123456'))
        for pts in range(self.view.THUMBNAIL_CACHE_LIMIT + 1):
            self.view.set_thumbnail(pts, image)
        self.assertEqual(
            self.view.thumbnail_cache_size(),
            self.view.THUMBNAIL_CACHE_LIMIT)

        self.view.set_thumbnail(30, image)
        self.view.set_filter('pending')
        tile = self.view.list_widget.item(0).icon().pixmap(
            self.view.list_widget.iconSize()).toImage()
        self.assertTrue(any(
            tile.pixelColor(x, y) == QColor(self.view._colors['warning'])
            for y in range(tile.height()) for x in range(tile.width())))

    def test_only_visible_uncached_tiles_are_requested(self):
        requested = []
        self.view.thumbnailsRequested.connect(
            lambda pts, size: requested.append((pts, size)))
        self.view.resize(230, 180)
        self.view.show()
        app.processEvents()
        self.view.request_visible_thumbnails()

        self.assertTrue(requested)
        self.assertTrue(set(requested[-1][0]) <= set(self.view.visible_pts()))
        self.assertGreater(requested[-1][1], 0)

    def test_clicking_a_tile_emits_its_pts(self):
        received = []
        self.view.frameActivated.connect(received.append)
        self.view.set_filter('annotated')
        self.view.list_widget.itemClicked.emit(self.view.list_widget.item(2))
        self.assertEqual(received, [20])

    def test_activating_an_unseen_frame_is_ignored(self):
        """The grid speaks for its tiles only, as the lanes view does."""
        received = []
        self.view.frameActivated.connect(received.append)
        self.view.activate_pts(10)
        self.assertEqual(received, [])

    def test_a_chip_selects_its_filter(self):
        self.view.chip_for('pending').click()
        self.assertEqual(self.view.filter_name(), 'pending')
        self.assertEqual(self.view.visible_pts(), [30])

    def test_apply_theme_does_not_raise(self):
        self.view.apply_theme(Theme.DARK)
        self.view.apply_theme(Theme.LIGHT)

    def test_tile_size_follows_the_display_scale(self):
        """Sizes frozen at import or in __init__ would stay 1x on hi-DPI.

        Both ends are pinned because the offscreen platform does not
        necessarily report exactly 96 logical DPI.
        """
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.0):
            self.view.set_filter('annotated')
            one_x = self.view.list_widget.iconSize().width()
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0):
            self.view.set_filter('annotated')
            two_x = self.view.list_widget.iconSize().width()
        self.assertEqual(two_x, one_x * 2)


if __name__ == '__main__':
    unittest.main()
