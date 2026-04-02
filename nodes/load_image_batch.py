import os
import re
import glob
import json
import random
import hashlib
import numpy as np
from PIL import Image, ImageOps
import torch

try:
    from server import PromptServer
except ImportError:
    PromptServer = None

try:
    import folder_paths
except ImportError:
    folder_paths = None

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


def get_sorted_image_paths(directory, image_filter='*'):
    # normpath first so UNC paths (//server/share) are handled correctly
    # by glob.escape (which can mangle raw UNC prefixes)
    directory = os.path.normpath(directory)
    paths = []
    for file_name in glob.glob(os.path.join(glob.escape(directory), image_filter), recursive=True):
        if file_name.lower().endswith(ALLOWED_EXT):
            paths.append(os.path.normpath(file_name))
    paths.sort(key=_natural_sort_key)
    return paths


def _save_preview_image(img):
    """Save a PIL image to ComfyUI's temp directory for node preview."""
    if folder_paths is None:
        return None
    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    suffix = ''.join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(5))
    filename = f"batch_ops_preview_{suffix}.png"
    img.save(os.path.join(temp_dir, filename), compress_level=1)
    return {"filename": filename, "subfolder": "", "type": "temp"}


class LoadImageBatch:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": ("STRING", {"default": '', "multiline": False, "tooltip": "Directory containing images to process."}),
                "image_filter": ("STRING", {"default": '*.*', "multiline": False, "tooltip": "Glob pattern to filter image filenames. Non-image files are always excluded. Examples: portrait_*, 2024-*, *.png"}),
                "auto_queue": ("BOOLEAN", {"default": False, "tooltip": "Automatically process all images in sequence. Re-queues after each image and stops when done."}),
                "index": ("INT", {"default": 0, "min": 0, "max": 150000, "step": 1, "tooltip": "Current position in the batch (read-only, updated automatically)."}),
                "include_extension": ("BOOLEAN", {"default": True, "tooltip": "Include file extension in the filename output (e.g. photo.png vs photo)."}),
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

    def load_image(self, path, image_filter='*',
                   auto_queue=False, index=0, include_extension=True,
                   unique_id=None):

        if not os.path.exists(path):
            raise ValueError(f"Path does not exist: {path}")

        image_paths = get_sorted_image_paths(path, image_filter)
        total = len(image_paths)

        if total == 0:
            raise ValueError(f"No images found in '{path}' matching filter '{image_filter}'")

        # use node's unique_id as the state key
        state_key = str(unique_id) if unique_id is not None else "default"

        # JSON is always the source of truth
        state = _load_state()
        stored = state.get(state_key, {})

        # reset if path or filter changed
        if stored.get('path') != path or stored.get('image_filter') != image_filter:
            idx = 0
        else:
            idx = stored.get('index', 0)

        # wrap around
        if idx >= total:
            idx = 0

        # persist next index
        next_idx = (idx + 1) % total
        state[state_key] = {'path': path, 'image_filter': image_filter, 'index': next_idx}
        _save_state(state)

        basename = os.path.basename(image_paths[idx])
        status = f"{idx + 1} / {total}  —  {basename}"
        print(f"[Batch Ops] node {state_key}: {status}")

        # mirror index to widget for display
        if PromptServer is not None and unique_id is not None:
            PromptServer.instance.send_sync("batch-ops-node-feedback", {
                "node_id": unique_id,
                "widget_name": "index",
                "type": "int",
                "value": idx,
            })

        # auto-queue: re-queue if not at the last image
        if auto_queue and PromptServer is not None:
            if idx < total - 1:
                PromptServer.instance.send_sync("batch-ops-add-queue", {})

        # load and process image
        img = Image.open(image_paths[idx])
        img = ImageOps.exif_transpose(img)

        if img.mode == 'RGBA':
            img = img.convert("RGB")

        filename = basename
        if not include_extension:
            filename = os.path.splitext(filename)[0]

        # build ui output
        ui = {"text": (status,)}
        preview = _save_preview_image(img)
        if preview is not None:
            ui["images"] = [preview]

        return {"ui": ui, "result": (pil2tensor(img), filename, idx, total)}

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # always re-execute since JSON state drives the index
        return float("NaN")
