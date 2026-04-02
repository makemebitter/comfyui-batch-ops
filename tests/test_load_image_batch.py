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


def _result(rv):
    """Extract the result tuple from the node's return dict."""
    return rv["result"]


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

    def test_image_filter(self, image_dir):
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
        fwd = image_dir.replace(os.sep, '/')
        paths = get_sorted_image_paths(fwd)
        assert len(paths) == 5

    def test_normpath_applied(self, image_dir):
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


class TestSequentialBehavior:
    def test_starts_at_zero(self, image_dir):
        node = LoadImageBatch()
        _, _, idx, _ = _result(node.load_image(image_dir, unique_id='1'))
        assert idx == 0

    def test_advances_each_call(self, image_dir):
        node = LoadImageBatch()
        indices = []
        for _ in range(5):
            _, _, idx, _ = _result(node.load_image(image_dir, unique_id='2'))
            indices.append(idx)
        assert indices == [0, 1, 2, 3, 4]

    def test_wraps_around(self, image_dir):
        node = LoadImageBatch()
        indices = []
        for _ in range(7):
            _, _, idx, _ = _result(node.load_image(image_dir, unique_id='3'))
            indices.append(idx)
        assert indices == [0, 1, 2, 3, 4, 0, 1]

    def test_different_nodes_independent(self, image_dir):
        node = LoadImageBatch()
        node.load_image(image_dir, unique_id='A')
        node.load_image(image_dir, unique_id='A')

        _, _, idx, _ = _result(node.load_image(image_dir, unique_id='B'))
        assert idx == 0

    def test_resets_on_path_change(self, image_dir):
        node = LoadImageBatch()
        node.load_image(image_dir, unique_id='10')
        node.load_image(image_dir, unique_id='10')

        d2 = tempfile.mkdtemp()
        try:
            Image.new('RGB', (32, 32), (0, 0, 0)).save(os.path.join(d2, 'img.png'))
            _, _, idx, _ = _result(node.load_image(d2, unique_id='10'))
            assert idx == 0
        finally:
            shutil.rmtree(d2)

    def test_resets_on_filter_change(self, image_dir):
        node = LoadImageBatch()
        node.load_image(image_dir, image_filter='*', unique_id='11')
        node.load_image(image_dir, image_filter='*', unique_id='11')

        _, _, idx, _ = _result(node.load_image(
            image_dir, image_filter='*.png', unique_id='11'))
        assert idx == 0

    def test_total_images_count(self, image_dir):
        node = LoadImageBatch()
        _, _, _, total = _result(node.load_image(image_dir, unique_id='12'))
        assert total == 5

    def test_filename_with_extension(self, image_dir):
        node = LoadImageBatch()
        _, filename, _, _ = _result(node.load_image(
            image_dir, include_extension=True, unique_id='13'))
        assert '.' in filename

    def test_filename_without_extension(self, image_dir):
        node = LoadImageBatch()
        _, filename, _, _ = _result(node.load_image(
            image_dir, include_extension=False, unique_id='14'))
        assert '.' not in filename


class TestUIOutput:
    def test_returns_status_text(self, image_dir):
        node = LoadImageBatch()
        rv = node.load_image(image_dir, unique_id='20')
        text = rv["ui"]["text"][0]
        assert "1 / 5" in text

    def test_status_text_includes_filename(self, image_dir):
        node = LoadImageBatch()
        rv = node.load_image(image_dir, unique_id='21')
        text = rv["ui"]["text"][0]
        assert "apple.png" in text

    def test_no_preview_without_folder_paths(self, image_dir):
        with patch('nodes.load_image_batch.folder_paths', None):
            node = LoadImageBatch()
            rv = node.load_image(image_dir, unique_id='22')
            assert "text" in rv["ui"]
            assert "images" not in rv["ui"]


class TestWidgetFeedback:
    def test_always_sends_index_feedback(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            node.load_image(image_dir, unique_id='42')
            calls = mock_server.instance.send_sync.call_args_list
            assert calls[0] == call("batch-ops-node-feedback", {
                "node_id": "42", "widget_name": "index", "type": "int", "value": 0,
            })

    def test_feedback_advances_with_state(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            node.load_image(image_dir, unique_id='42')
            mock_server.reset_mock()
            node.load_image(image_dir, unique_id='42')
            calls = mock_server.instance.send_sync.call_args_list
            assert calls[0] == call("batch-ops-node-feedback", {
                "node_id": "42", "widget_name": "index", "type": "int", "value": 1,
            })


class TestAutoQueue:
    def test_requeues_mid_batch(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            node.load_image(image_dir, auto_queue=True, unique_id='50')
            call_names = [c[0][0] for c in mock_server.instance.send_sync.call_args_list]
            assert "batch-ops-add-queue" in call_names

    def test_stops_at_last_image(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            for _ in range(4):
                node.load_image(image_dir, auto_queue=True, unique_id='51')
            mock_server.reset_mock()

            node.load_image(image_dir, auto_queue=True, unique_id='51')
            call_names = [c[0][0] for c in mock_server.instance.send_sync.call_args_list]
            assert "batch-ops-add-queue" not in call_names

    def test_full_batch_run(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            requeue_count = 0
            for _ in range(5):
                mock_server.reset_mock()
                node.load_image(image_dir, auto_queue=True, unique_id='52')
                call_names = [c[0][0] for c in mock_server.instance.send_sync.call_args_list]
                if "batch-ops-add-queue" in call_names:
                    requeue_count += 1
            assert requeue_count == 4

    def test_json_persists_during_auto_queue(self, image_dir):
        mock_server = MagicMock()
        with patch('nodes.load_image_batch.PromptServer', mock_server):
            node = LoadImageBatch()
            for _ in range(3):
                node.load_image(image_dir, auto_queue=True, unique_id='53')

        with patch('nodes.load_image_batch.PromptServer', None):
            node2 = LoadImageBatch()
            _, _, idx, _ = _result(node2.load_image(
                image_dir, auto_queue=True, unique_id='53'))
            assert idx == 3

    def test_no_crash_without_prompt_server(self, image_dir):
        with patch('nodes.load_image_batch.PromptServer', None):
            node = LoadImageBatch()
            _, _, idx, _ = _result(node.load_image(
                image_dir, auto_queue=True, unique_id='54'))
            assert idx == 0


class TestRGBAHandling:
    def test_rgba_auto_converted_to_rgb(self, rgba_image_dir):
        node = LoadImageBatch()
        image, _, _, _ = _result(node.load_image(rgba_image_dir, unique_id='60'))
        assert image.shape[3] == 3

    def test_rgb_stays_rgb(self, image_dir):
        node = LoadImageBatch()
        image, _, _, _ = _result(node.load_image(image_dir, unique_id='61'))
        assert image.shape[3] == 3


class TestErrorHandling:
    def test_invalid_path_raises(self):
        node = LoadImageBatch()
        with pytest.raises(ValueError, match="Path does not exist"):
            node.load_image('/nonexistent/path/12345', unique_id='70')

    def test_no_images_raises(self):
        d = tempfile.mkdtemp()
        try:
            node = LoadImageBatch()
            with pytest.raises(ValueError, match="No images found"):
                node.load_image(d, unique_id='71')
        finally:
            shutil.rmtree(d)

    def test_no_matching_filter_raises(self, image_dir):
        node = LoadImageBatch()
        with pytest.raises(ValueError, match="No images found"):
            node.load_image(image_dir, image_filter='*.xyz', unique_id='72')


class TestIsChanged:
    def test_always_nan(self, image_dir):
        result = LoadImageBatch.IS_CHANGED(
            path=image_dir, image_filter='*',
            auto_queue=False, index=0, include_extension=True
        )
        assert result != result  # NaN != NaN
