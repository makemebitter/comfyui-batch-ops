# ComfyUI Batch Ops

A collection of batch operation nodes for [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

## Nodes

### Image Batch Runner

Iterates through images in a directory, one per queue run. Supports auto-queue for fully automated batch processing, and resumes across sessions.

#### Inputs

| Input | Type | Description |
|---|---|---|
| `path` | STRING | Directory containing images |
| `filename_filter` | STRING | Glob pattern to filter filenames (default: `*`). Only image files are loaded regardless of filter. Examples: `portrait_*`, `2024-*`, `*.png` |
| `batch_id` | STRING | Identifies this batch for state tracking. Different `batch_id`s track position independently |
| `auto_queue` | BOOLEAN | When enabled, automatically processes all images then stops |
| `index` | INT | Display-only — shows current position in the batch (read-only, updated automatically) |
| `include_extension` | BOOLEAN | Include file extension in the filename output |

#### Outputs

| Output | Type | Description |
|---|---|---|
| `image` | IMAGE | The loaded image (always RGB) |
| `filename` | STRING | Filename of the loaded image |
| `current_index` | INT | Current position in the batch |
| `total_images` | INT | Total number of images matched |

#### On-Node Display

The node shows a thumbnail preview and status text (e.g. `3 / 47  —  photo.png`) directly on itself. No need to attach separate preview or text nodes.

#### How It Works

Each queue run loads the next image. Position is saved to a JSON file on disk, so progress survives browser crashes, ComfyUI restarts, and workflow reloads.

- **Manual stepping**: Queue each run yourself (or use ComfyUI's auto-queue feature)
- **Auto-queue**: Toggle `auto_queue` on — the node re-queues itself after each image and stops when all images are processed
- **Resume**: Close ComfyUI, come back later, queue again — picks up where you left off
- **Reset**: Change the `path`, `filename_filter`, or `batch_id` to reset position to 0

#### Sorting

Images are sorted using natural sort order (matching Windows Explorer), so `img2.png` comes before `img10.png`.

#### Network Paths

UNC paths (`//server/share/images`) are fully supported.

## Installation

Clone into your ComfyUI `custom_nodes` directory:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/makemebitter/comfyui-batch-ops.git
```

Restart ComfyUI. The node appears under **Batch Ops → Image Batch Runner**.

## Testing

### Unit tests

```bash
pip install pytest
python -m pytest tests/ -v
```

### E2E testing with ComfyUI

1. Install the node pack (see above)
2. Start ComfyUI
3. Run:

```bash
python tests/test_e2e.py --comfyui-url http://127.0.0.1:8188 --image-dir /path/to/test/images
```

## License

MIT
