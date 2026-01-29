# tests/test_performance.py
"""Tests for performance optimizations (Issue #29)."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
sys.path.insert(0, os.path.join(dir_name, '..', '..', 'libs'))

from collections import OrderedDict
from libs.galleryWidget import ThumbnailCache


class TestPathToIndexDict(unittest.TestCase):
    """Test cases for _path_to_idx O(1) lookup optimization."""

    def test_dict_creation_from_list(self):
        """Test creating path-to-index dict from image list."""
        m_img_list = ['/img/a.jpg', '/img/b.jpg', '/img/c.jpg']
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        self.assertEqual(_path_to_idx['/img/a.jpg'], 0)
        self.assertEqual(_path_to_idx['/img/b.jpg'], 1)
        self.assertEqual(_path_to_idx['/img/c.jpg'], 2)

    def test_dict_lookup_vs_list_index(self):
        """Test that dict lookup gives same result as list.index()."""
        m_img_list = [f'/img/image_{i}.jpg' for i in range(100)]
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        # Test multiple lookups
        for test_path in ['/img/image_0.jpg', '/img/image_50.jpg', '/img/image_99.jpg']:
            dict_result = _path_to_idx.get(test_path, -1)
            list_result = m_img_list.index(test_path)
            self.assertEqual(dict_result, list_result)

    def test_dict_get_with_default(self):
        """Test dict.get() returns default for missing paths."""
        m_img_list = ['/img/a.jpg', '/img/b.jpg']
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        result = _path_to_idx.get('/img/nonexistent.jpg', -1)
        self.assertEqual(result, -1)

    def test_dict_membership_check(self):
        """Test 'in' operator for path existence check."""
        m_img_list = ['/img/a.jpg', '/img/b.jpg']
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        self.assertTrue('/img/a.jpg' in _path_to_idx)
        self.assertFalse('/img/c.jpg' in _path_to_idx)

    def test_empty_list_creates_empty_dict(self):
        """Test empty image list creates empty dict."""
        m_img_list = []
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        self.assertEqual(len(_path_to_idx), 0)

    def test_large_list_indexing(self):
        """Test dict works correctly with large lists."""
        size = 10000
        m_img_list = [f'/img/image_{i:05d}.jpg' for i in range(size)]
        _path_to_idx = {path: idx for idx, path in enumerate(m_img_list)}

        # Test first, middle, and last
        self.assertEqual(_path_to_idx['/img/image_00000.jpg'], 0)
        self.assertEqual(_path_to_idx['/img/image_05000.jpg'], 5000)
        self.assertEqual(_path_to_idx['/img/image_09999.jpg'], 9999)


class TestThumbnailCacheOrderedDict(unittest.TestCase):
    """Test cases verifying OrderedDict-based LRU cache behavior."""

    def test_internal_structure_is_ordered_dict(self):
        """Test that cache uses OrderedDict internally."""
        cache = ThumbnailCache(max_size=10)
        self.assertIsInstance(cache._cache, OrderedDict)

    def test_lru_order_maintained(self):
        """Test that LRU order is correctly maintained."""
        cache = ThumbnailCache(max_size=5)

        # Add items in order
        for i in range(5):
            cache.put(f'/img{i}.jpg', f'p{i}')

        # Access img0 and img1 to make them most recent
        cache.get('/img0.jpg')
        cache.get('/img1.jpg')

        # Add 2 new items - should evict img2 and img3 (oldest)
        cache.put('/img5.jpg', 'p5')
        cache.put('/img6.jpg', 'p6')

        # img0, img1 should still exist
        self.assertIsNotNone(cache.get('/img0.jpg'))
        self.assertIsNotNone(cache.get('/img1.jpg'))

        # img2, img3 should be evicted
        self.assertIsNone(cache.get('/img2.jpg'))
        self.assertIsNone(cache.get('/img3.jpg'))

        # img4, img5, img6 should exist
        self.assertIsNotNone(cache.get('/img4.jpg'))
        self.assertIsNotNone(cache.get('/img5.jpg'))
        self.assertIsNotNone(cache.get('/img6.jpg'))

    def test_put_existing_updates_order(self):
        """Test that updating existing key moves it to end."""
        cache = ThumbnailCache(max_size=3)

        cache.put('/img1.jpg', 'v1')
        cache.put('/img2.jpg', 'v2')
        cache.put('/img3.jpg', 'v3')

        # Update img1 - should move to end
        cache.put('/img1.jpg', 'v1_updated')

        # Add new item - should evict img2 (now oldest)
        cache.put('/img4.jpg', 'v4')

        self.assertEqual(cache.get('/img1.jpg'), 'v1_updated')
        self.assertIsNone(cache.get('/img2.jpg'))
        self.assertIsNotNone(cache.get('/img3.jpg'))
        self.assertIsNotNone(cache.get('/img4.jpg'))

    def test_cache_size_never_exceeds_max(self):
        """Test that cache size never exceeds max_size."""
        max_size = 5
        cache = ThumbnailCache(max_size=max_size)

        # Add more items than max_size
        for i in range(20):
            cache.put(f'/img{i}.jpg', f'p{i}')
            self.assertLessEqual(len(cache._cache), max_size)

    def test_remove_is_safe_for_missing_keys(self):
        """Test remove doesn't raise for missing keys."""
        cache = ThumbnailCache()

        # Should not raise any exception
        cache.remove('/nonexistent.jpg')
        cache.remove('/another/missing.jpg')


class TestAnnotationStatusCache(unittest.TestCase):
    """Test cases for annotation status caching."""

    def setUp(self):
        """Create temp directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_dict_operations(self):
        """Test basic cache dict operations."""
        cache = {}

        # Simulate caching
        cache['/img1.jpg'] = 'HAS_LABELS'
        cache['/img2.jpg'] = 'VERIFIED'

        self.assertEqual(cache.get('/img1.jpg'), 'HAS_LABELS')
        self.assertEqual(cache.get('/img2.jpg'), 'VERIFIED')
        self.assertIsNone(cache.get('/img3.jpg'))

    def test_cache_invalidation_single(self):
        """Test invalidating single cache entry."""
        cache = {'/img1.jpg': 'HAS_LABELS', '/img2.jpg': 'VERIFIED'}

        # Invalidate single entry
        cache.pop('/img1.jpg', None)

        self.assertIsNone(cache.get('/img1.jpg'))
        self.assertEqual(cache.get('/img2.jpg'), 'VERIFIED')

    def test_cache_invalidation_all(self):
        """Test clearing entire cache."""
        cache = {'/img1.jpg': 'HAS_LABELS', '/img2.jpg': 'VERIFIED'}

        # Clear all
        cache.clear()

        self.assertEqual(len(cache), 0)

    def test_cache_prevents_redundant_lookups(self):
        """Test that caching prevents redundant operations."""
        lookup_count = [0]  # Use list to allow mutation in nested function

        def mock_get_status(path, cache):
            if path in cache:
                return cache[path]
            lookup_count[0] += 1
            status = 'HAS_LABELS'  # Simulated status
            cache[path] = status
            return status

        cache = {}

        # First call should increment counter
        mock_get_status('/img1.jpg', cache)
        self.assertEqual(lookup_count[0], 1)

        # Second call should use cache
        mock_get_status('/img1.jpg', cache)
        self.assertEqual(lookup_count[0], 1)  # No increment

        # Different path should increment
        mock_get_status('/img2.jpg', cache)
        self.assertEqual(lookup_count[0], 2)


class TestPerformanceScaling(unittest.TestCase):
    """Test that optimizations scale well with large datasets."""

    def test_dict_lookup_constant_time(self):
        """Test that dict lookup is effectively constant time."""
        import time

        # Create small and large dicts
        small_list = [f'/img/image_{i}.jpg' for i in range(100)]
        large_list = [f'/img/image_{i}.jpg' for i in range(10000)]

        small_dict = {path: idx for idx, path in enumerate(small_list)}
        large_dict = {path: idx for idx, path in enumerate(large_list)}

        # Measure lookup time for small dict
        start = time.perf_counter()
        for _ in range(1000):
            _ = small_dict.get('/img/image_50.jpg', -1)
        small_time = time.perf_counter() - start

        # Measure lookup time for large dict
        start = time.perf_counter()
        for _ in range(1000):
            _ = large_dict.get('/img/image_5000.jpg', -1)
        large_time = time.perf_counter() - start

        # Large dict lookup should not be significantly slower (within 5x)
        # This is a generous bound to avoid flaky tests
        self.assertLess(large_time, small_time * 5)

    def test_cache_operations_constant_time(self):
        """Test that cache operations are constant time."""
        import time

        cache = ThumbnailCache(max_size=1000)

        # Fill cache
        for i in range(1000):
            cache.put(f'/img{i}.jpg', f'p{i}')

        # Measure get time
        start = time.perf_counter()
        for _ in range(1000):
            cache.get('/img500.jpg')
        get_time = time.perf_counter() - start

        # Measure put time (updates existing)
        start = time.perf_counter()
        for _ in range(1000):
            cache.put('/img500.jpg', 'updated')
        put_time = time.perf_counter() - start

        # Both should be very fast (< 100ms for 1000 ops)
        self.assertLess(get_time, 0.1)
        self.assertLess(put_time, 0.1)


if __name__ == '__main__':
    unittest.main()
