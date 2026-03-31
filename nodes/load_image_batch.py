import os
import re
import glob
import json
import hashlib
import numpy as np
from PIL import Image, ImageOps
import torch

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

ALLOWED_EXT = ('.jpeg', '.jpg', '.png', '.tiff', '.gif', '.bmp', '.webp')

# Simple file-based counter storage
COUNTER_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "batch_state.json")


def _load_state():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, 'r') as f:
            return json.load(f)
    return {}


def _save_state(state):
    with open(COUNTER_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def pil2tensor(image):
    return torch.from_numpy(np.array(image).astype(np.float32) / 255.0).unsqueeze(0)


def get_sha256(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, 'rb') as file:
        for chunk in iter(lambda: file.read(4096), b''):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def _natural_sort_key(path):
    """Sort key that matches Windows Explorer ordering.
    Splits filename into text and numeric chunks so 'img2' < 'img10'."""
    basename = os.path.basename(path).lower()
    parts = re.split(r'(\d+)', basename)
    return [int(p) if p.isdigit() else p for p in parts]


def get_sorted_image_paths(directory, pattern='*'):
    # normpath first so UNC paths (//server/share) are handled correctly
    # by glob.escape (which can mangle raw UNC prefixes)
    directory = os.path.normpath(directory)
    paths = []
    for file_name in glob.glob(os.path.join(glob.escape(directory), pattern), recursive=True):
        if file_name.lower().endswith(ALLOWED_EXT):
            paths.append(os.path.normpath(file_name))
    paths.sort(key=_natural_sort_key)
    return paths


class LoadImageBatch:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": ("STRING", {"default": '', "multiline": False}),
                "pattern": ("STRING", {"default": '*', "multiline": False}),
                "mode": (["index", "sequential"],),
                "index": ("INT", {"default": 0, "min": 0, "max": 150000, "step": 1}),
                "batch_id": ("STRING", {"default": 'batch_001', "multiline": False}),
                "auto_queue": ("BOOLEAN", {"default": False}),
                "convert_to_rgb": ("BOOLEAN", {"default": True}),
                "include_extension": ("BOOLEAN", {"default": True}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT", "INT")
    RETURN_NAMES = ("image", "filename", "current_index", "total_images")
    FUNCTION = "load_image"
    CATEGORY = "Batch Ops"
    OUTPUT_NODE = True

    def load_image(self, path, pattern='*', mode='index', index=0, batch_id='batch_001',
                   auto_queue=False, convert_to_rgb=True, include_extension=True,
                   unique_id=None):

        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        image_paths = get_sorted_image_paths(path, pattern)
        total = len(image_paths)

        if total == 0:
            raise ValueError(f"No images found in '{path}' matching pattern '{pattern}'")

        if mode == 'index':
            idx = index % total
        else:
            # sequential mode: restore persisted index
            state = _load_state()
            key = batch_id
            stored = state.get(key, {})

            # reset if path or pattern changed
            if stored.get('path') != path or stored.get('pattern') != pattern:
                idx = 0
            else:
                idx = stored.get('index', 0)

            # wrap around
            if idx >= total:
                idx = 0

            # persist next index
            next_idx = (idx + 1) % total
            state[key] = {'path': path, 'pattern': pattern, 'index': next_idx}
            _save_state(state)

            print(f"[Batch Ops] {batch_id}: loading {idx + 1}/{total} — {os.path.basename(image_paths[idx])}")

            # auto-queue: mirror index to widget and re-queue if not done
            if auto_queue and PromptServer is not None:
                is_last = (idx == total - 1)

                # update index widget to show current position
                PromptServer.instance.send_sync("batch-ops-node-feedback", {
                    "node_id": unique_id,
                    "widget_name": "index",
                    "type": "int",
                    "value": idx,
                })

                if not is_last:
                    PromptServer.instance.send_sync("batch-ops-add-queue", {})

        # load and process image
        img = Image.open(image_paths[idx])
        img = ImageOps.exif_transpose(img)

        if convert_to_rgb:
            img = img.convert("RGB")

        filename = os.path.basename(image_paths[idx])
        if not include_extension:
            filename = os.path.splitext(filename)[0]

        return (pil2tensor(img), filename, idx, total)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if kwargs['mode'] != 'index':
            return float("NaN")
        path = kwargs['path']
        pattern = kwargs['pattern']
        image_paths = get_sorted_image_paths(path, pattern)
        if not image_paths:
            return float("NaN")
        total = len(image_paths)
        idx = kwargs['index'] % total
        return get_sha256(image_paths[idx])
