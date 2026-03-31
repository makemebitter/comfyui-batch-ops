# ComfyUI Batch Ops

A collection of batch operation nodes for [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

## Nodes

### Load Image Batch

A redesigned batch image loader with two clean modes, auto-queue support, and resume capability.

#### Inputs

| Input | Type | Description |
|---|---|---|
| `path` | STRING | Directory containing images |
| `pattern` | STRING | Glob pattern to filter files (default: `*`) |
| `mode` | ENUM | `index` or `sequential` |
| `index` | INT | Image index (used in `index` mode, display-only in `sequential`) |
| `batch_id` | STRING | State key for sequential mode (used in `sequential` mode) |
| `auto_queue` | BOOLEAN | Automatically process all images (used in `sequential` mode) |
| `convert_to_rgb` | BOOLEAN | Strip alpha channel (default: true) |
| `include_extension` | BOOLEAN | Include file extension in filename output (default: true) |

#### Outputs

| Output | Type | Description |
|---|---|---|
| `image` | IMAGE | The loaded image |
| `filename` | STRING | Filename of the loaded image |
| `current_index` | INT | Index of the loaded image |
| `total_images` | INT | Total number of images in the directory |

#### Modes

**Index mode** — Load a specific image by index. Use ComfyUI's built-in `control_after_generate` on the index widget to step through images (increment), pick random ones (randomize), or stay fixed.

**Sequential mode** — Automatically advances through images one per queue run. State is persisted to disk, so you can resume across sessions. Use `batch_id` to track multiple independent batches.

**Auto-queue** — Enable `auto_queue` in sequential mode to process every image in the directory automatically. The node re-queues itself after each image and stops when the batch is complete. If the browser disconnects mid-batch, progress is saved and you can resume later.

#### Sorting

Images are sorted using natural sort order (matching Windows Explorer), so `img2.png` comes before `img10.png`.

## Installation

### Manual

Clone this repository into your ComfyUI `custom_nodes` directory:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/makemebitter/comfyui-batch-ops.git
```

Then restart ComfyUI.

### Development (symlink)

```bash
# Windows (run as administrator)
mklink /D "C:\path\to\ComfyUI\custom_nodes\comfyui-batch-ops" "C:\path\to\comfyui-batch-ops"

# Linux/macOS
ln -s /path/to/comfyui-batch-ops /path/to/ComfyUI/custom_nodes/comfyui-batch-ops
```

## Testing

### Unit tests

```bash
pip install pytest
python -m pytest tests/ -v
```

### E2E testing with ComfyUI

1. Install the node pack (see above)
2. Start ComfyUI
3. Run the e2e test script:

```bash
python tests/test_e2e.py --comfyui-url http://127.0.0.1:8188 --image-dir /path/to/test/images
```

This submits a workflow via ComfyUI's API and verifies the output.

## License

MIT
