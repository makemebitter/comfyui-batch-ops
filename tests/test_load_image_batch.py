import os
import sys
import json
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch, call
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from nodes.load_image_batch import LoadImageBatch, get_sorted_image_paths, COUNTER_FILE


@pytest.fixture
def image_dir():
    """Create a temp directory with test images."""
    d = tempfile.mkdtemp()
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (128, 128, 128)]
    names = ['apple.png', 'banana.jpg', 'cherry.png', 'date.bmp', 'elderberry.webp']
    for name, color in zip(names, colors):
        img = Image.new('RGB', (64, 64), color)
        img.save(os.path.join(d, name))
    yield d
    shutil.rmtree(d)


@pytest.fixture
def rgba_image_dir():
    """Create a temp directory with an RGBA image."""
    d = tempfile.mkdtemp()
    img = Image.new('RGBA', (64, 64), (255, 0, 0, 128))
    img.save(os.path.join(d, 'transparent.png'))
    yield d
    shutil.rmtree(d)


@pytest.fixture(autouse=True)
def clean_state():
    """Remove state file before/after each test."""
    if os.path.exists(COUNTER_FILE):
        os.remove(COUNTER_FILE)
    yield
    if os.path.exists(COUNTER_FILE):
        os.remove(COUNTER_FILE)


class TestGetSortedImagePaths:
    def test_finds_all_images(self, image_dir):
        paths = get_sorted_image_paths(image_dir)
        assert len(paths) == 5

    def test_sorted_alphabetically(self, image_dir):
        paths = get_sorted_image_paths(image_dir)
        basenames = [os.path.basename(p) for p in paths]
        assert basenames == sorted(basenames)

    def test_pattern_filter(self, image_dir):
        paths = get_sorted_image_paths(image_dir, '*.png')
        basenames = [os.path.basename(p) for p in paths]
        assert all(n.endswith('.png') for n in basenames)
        assert len(basenames) == 2

    def test_natural_sort_order(self):
        """Ensure ordering matches Windows Explorer (img2 before img10)."""
        d = tempfile.mkdtemp()
        try:
            for name in ['img10.png', 'img2.png', 'img1.png', 'img20.png', 'img3.png']:
                Image.new('RGB', (8, 8)).save(os.path.join(d, name))
            paths = get_sorted_image_paths(d)
            basenames = [os.path.basename(p) for p in paths]
            assert basenames == ['img1.png', 'img2.png', 'img3.png', 'img10.png', 'img20.png']
        finally:
            shutil.rmtree(d)

    def test_empty_dir(self):
        d = tempfile.mkdtemp()
        try:
            paths = get_sorted_image_paths(d)
            assert paths == []
        finally:
            shutil.rmtree(d)

    def test_forward_slash_paths(self, image_dir):
        """Forward-slash paths (including UNC-style) should work."""
        fwd = image_dir.replace(os.sep, '/')
        paths = get_sorted_image_paths(fwd)
        assert len(paths) == 5

    def test_normpath_applied(self, image_dir):
        """Paths with redundant separators or dots should be normalized."""
        messy = os.path.join(image_dir, '.', '')
        paths = get_sorted_image_paths(messy)
        assert len(paths) == 5

    def test_ignores_non_image_files(self):
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, 'readme.txt'), 'w') as f:
                f.write('hello')
            with open(os.path.join(d, 'data.csv'), 'w') as f:
                f.write('a,b,c')
            paths = get_sorted_image_paths(d)
            assert paths == []
        finally:
            shutil.rmtree(d)


class TestIndexMode:
    def test_load_first_image(self, image_dir):
        node = LoadImageBatch()
        image, filename, idx, total = node.load_image(image_dir, index=0)
        assert image.shape[0] == 1  # batch dim
        assert image.shape[3] == 3  # RGB
        assert idx == 0
        assert total == 5

    def test_load_specific_index(self, image_dir):
        node = LoadImageBatch()
        _, filename, idx, _ = node.load_image(image_dir, index=2)
        assert idx == 2

    def test_index_wraps_around(self, image_dir):
        node = LoadImageBatch()
        _, _, idx, total = node.load_image(image_dir, index=7)
        assert idx == 7 % total

    def test_filename_with_extension(self, image_dir):
        node = LoadImageBatch()
        _, filename, _, _ = node.load_image(image_dir, index=0, include_extension=True)
        assert '.' in filename

    def test_filename_without_extension(self, image_dir):
        node = LoadImageBatch()
        _, filename, _, _ = node.load_image(image_dir, index=0, include_extension=False)
        assert '.' not in filename

    def test_total_images_count(self, image_dir):
        node = LoadImageBatch()
        _, _, _, total = node.load_image(image_dir)
        assert total == 5


class TestSequentialMode:
    def test_starts_at_zero(self, image_dir):
        node = LoadImageBatch()
        _, _, idx, _ = node.load_image(image_dir, mode='sequential', batch_id='test1')
        assert idx == 0

    def test_advances_each_call(self, image_dir):
        node = LoadImageBatch()
        indices = []
        for _ in range(5):
            _, _, idx, _ = node.load_image(image_dir, mode='sequential', batch_id='test2')
            indices.append(idx)
        assert indices == [0, 1, 2, 3, 4]

    def test_wraps_around(self, image_dir):
        node = LoadImageBatch()
        indices = []
        for _ in range(7):
            _, _, idx, _ = node.load_image(image_dir, mode='sequential', batch_id='test3')
            indices.append(idx)
        assert indices == [0, 1, 2, 3, 4, 0, 1]

    def test_different_batch_ids_independent(self, image_dir):
        node = LoadImageBatch()
        # advance batch A twice
        node.load_image(image_dir, mode='sequential', batch_id='A')
        node.load_image(image_dir, mode='sequential', batch_id='A')

        # batch B should still start at 0
        _, _, idx, _ = node.load_image(image_dir, mode='sequential', batch_id='B')
        assert idx == 0

    def test_resets_on_path_change(self, image_dir):
        node = LoadImageBatch()
        # advance a few times
        node.load_image(image_dir, mode='sequential', batch_id='reset_test')
        node.load_image(image_dir, mode='sequential', batch_id='reset_test')

        # create new dir and use same batch_id
        d2 = tempfile.mkdtemp()
        try:
            img = Image.new('RGB', (32, 32), (0, 0, 0))
            img.save(os.path.join(d2, 'img.png'))
            _, _, idx, _ = node.load_image(d2, mode='sequential', batch_id='reset_test')
            assert idx == 0
        finally:
            shutil.rmtree(d2)

    def test_resets_on_pattern_change(self, image_dir):
        node = LoadImageBatch()
        node.load_image(image_dir, mode='sequential', batch_id='pat_test', pattern='*')
        node.load_image(image_dir, mode='sequential', batch_id='pat_test', pattern='*')

        # change pattern — should reset
        _, _, idx, _ = node.load_image(image_dir, mode='sequential', batch_id='pat_test', pattern='*.png')
        assert idx == 0


class TestAutoQueue:
    def test_sends_feedback_and_requeues_mid_batch(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            _, _, idx, _ = node.load_image(
                image_dir, mode='sequential', batch_id='aq1',
                auto_queue=True, unique_id='42'
            )
            assert idx == 0
            calls = mock_server.instance.send_sync.call_args_list
            # should send feedback with current index
            assert calls[0] == call("batch-ops-node-feedback", {
                "node_id": "42", "widget_name": "index", "type": "int", "value": 0,
            })
            # should re-queue
            assert calls[1] == call("batch-ops-add-queue", {})

    def test_stops_at_last_image(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            # advance to last image
            for _ in range(4):
                node.load_image(image_dir, mode='sequential', batch_id='aq2',
                                auto_queue=True, unique_id='42')
            mock_server.reset_mock()

            # this is the 5th (last) image
            _, _, idx, _ = node.load_image(
                image_dir, mode='sequential', batch_id='aq2',
                auto_queue=True, unique_id='42'
            )
            assert idx == 4
            calls = mock_server.instance.send_sync.call_args_list
            # should send feedback but NOT re-queue
            assert calls[0] == call("batch-ops-node-feedback", {
                "node_id": "42", "widget_name": "index", "type": "int", "value": 4,
            })
            assert len(calls) == 1  # no add-queue

    def test_full_batch_run(self, image_dir):
        """Simulate a full auto-queue batch: 5 images, should re-queue 4 times then stop."""
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            requeue_count = 0
            for i in range(5):
                mock_server.reset_mock()
                node.load_image(
                    image_dir, mode='sequential', batch_id='aq_full',
                    auto_queue=True, unique_id='99'
                )
                calls = mock_server.instance.send_sync.call_args_list
                call_names = [c[0][0] for c in calls]
                if "batch-ops-add-queue" in call_names:
                    requeue_count += 1
            assert requeue_count == 4  # re-queued for images 0-3, not for image 4

    def test_json_state_persists_during_auto_queue(self, image_dir):
        """Auto-queue should write to JSON so resume works if browser disconnects."""
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            # process 3 images
            for _ in range(3):
                node.load_image(
                    image_dir, mode='sequential', batch_id='aq_persist',
                    auto_queue=True, unique_id='10'
                )

        # simulate browser disconnect — no PromptServer, fresh node
        with patch('nodes.load_image_batch.PromptServer', None):
            node2 = LoadImageBatch()
            _, _, idx, _ = node2.load_image(
                image_dir, mode='sequential', batch_id='aq_persist',
                auto_queue=True
            )
            # should resume from index 3
            assert idx == 3

    def test_no_effect_in_index_mode(self, image_dir):
        """auto_queue should be ignored in index mode."""
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            node.load_image(image_dir, mode='index', index=0,
                            auto_queue=True, unique_id='50')
            mock_server.instance.send_sync.assert_not_called()

    def test_no_crash_without_prompt_server(self, image_dir):
        """auto_queue should work silently when PromptServer is unavailable."""
        with patch('nodes.load_image_batch.PromptServer', None):
            node = LoadImageBatch()
            _, _, idx, _ = node.load_image(
                image_dir, mode='sequential', batch_id='aq_no_server',
                auto_queue=True
            )
            assert idx == 0  # still loads fine


class TestRGBAHandling:
    def test_convert_to_rgb(self, rgba_image_dir):
        node = LoadImageBatch()
        image, _, _, _ = node.load_image(rgba_image_dir, convert_to_rgb=True)
        assert image.shape[3] == 3

    def test_keep_rgba(self, rgba_image_dir):
        node = LoadImageBatch()
        image, _, _, _ = node.load_image(rgba_image_dir, convert_to_rgb=False)
        assert image.shape[3] == 4


class TestErrorHandling:
    def test_invalid_path_raises(self):
        node = LoadImageBatch()
        with pytest.raises(ValueError, match="Path does not exist"):
            node.load_image('/nonexistent/path/12345')

    def test_no_images_raises(self):
        d = tempfile.mkdtemp()
        try:
            node = LoadImageBatch()
            with pytest.raises(ValueError, match="No images found"):
                node.load_image(d)
        finally:
            shutil.rmtree(d)

    def test_no_matching_pattern_raises(self, image_dir):
        node = LoadImageBatch()
        with pytest.raises(ValueError, match="No images found"):
            node.load_image(image_dir, pattern='*.xyz')


class TestIsChanged:
    def test_sequential_always_nan(self, image_dir):
        result = LoadImageBatch.IS_CHANGED(
            path=image_dir, pattern='*', mode='sequential',
            index=0, batch_id='test', auto_queue=False,
            convert_to_rgb=True, include_extension=True
        )
        assert result != result  # NaN != NaN

    def test_index_returns_hash(self, image_dir):
        result = LoadImageBatch.IS_CHANGED(
            path=image_dir, pattern='*', mode='index',
            index=0, batch_id='test', auto_queue=False,
            convert_to_rgb=True, include_extension=True
        )
        assert isinstance(result, str)
        assert len(result) == 64  # sha256 hex

    def test_different_index_different_hash(self, image_dir):
        r1 = LoadImageBatch.IS_CHANGED(
            path=image_dir, pattern='*', mode='index',
            index=0, batch_id='test', auto_queue=False,
            convert_to_rgb=True, include_extension=True
        )
        r2 = LoadImageBatch.IS_CHANGED(
            path=image_dir, pattern='*', mode='index',
            index=1, batch_id='test', auto_queue=False,
            convert_to_rgb=True, include_extension=True
        )
        assert r1 != r2
