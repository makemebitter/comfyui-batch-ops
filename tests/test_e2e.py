"""
E2E test for Load Image Batch node against a running ComfyUI instance.

Usage:
    python tests/test_e2e.py --comfyui-url http://127.0.0.1:8188 --image-dir /path/to/images

Prerequisites:
    - ComfyUI running with comfyui-batch-ops installed
    - A directory with at least 2 images
"""
import argparse
import json
import time
import urllib.request
import urllib.error
import sys
import os


def build_workflow(image_dir, mode="index", index=0, batch_id="e2e_test"):
    """Build a minimal ComfyUI workflow that runs Load Image Batch."""
    return {
        "1": {
            "class_type": "Load Image Batch",
            "inputs": {
                "path": image_dir,
                "pattern": "*",
                "mode": mode,
                "index": index,
                "batch_id": batch_id,
                "auto_queue": False,
                "convert_to_rgb": True,
                "include_extension": True,
            },
        },
        # PreviewImage is an output node so the workflow actually executes
        "2": {
            "class_type": "PreviewImage",
            "inputs": {
                "images": ["1", 0],
            },
        },
    }


def submit_prompt(base_url, workflow):
    """Submit a workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{base_url}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    return result["prompt_id"]


def wait_for_completion(base_url, prompt_id, timeout=30):
    """Poll /history until the prompt is done."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/history/{prompt_id}")
            with urllib.request.urlopen(req) as resp:
                history = json.loads(resp.read())
            if prompt_id in history:
                return history[prompt_id]
        except urllib.error.HTTPError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"Prompt {prompt_id} did not complete within {timeout}s")


def test_index_mode(base_url, image_dir):
    """Test loading a specific image by index."""
    print("[TEST] Index mode... ", end="", flush=True)
    workflow = build_workflow(image_dir, mode="index", index=0)
    prompt_id = submit_prompt(base_url, workflow)
    result = wait_for_completion(base_url, prompt_id)

    status = result.get("status", {})
    if status.get("status_str") != "success":
        print(f"FAIL — status: {status}")
        return False

    print("PASS")
    return True


def test_sequential_mode(base_url, image_dir):
    """Test sequential mode advances through images."""
    print("[TEST] Sequential mode (2 runs)... ", end="", flush=True)
    batch_id = f"e2e_seq_{int(time.time())}"

    for i in range(2):
        workflow = build_workflow(image_dir, mode="sequential", batch_id=batch_id)
        prompt_id = submit_prompt(base_url, workflow)
        result = wait_for_completion(base_url, prompt_id)

        status = result.get("status", {})
        if status.get("status_str") != "success":
            print(f"FAIL on run {i} — status: {status}")
            return False

    print("PASS")
    return True


def test_node_registered(base_url):
    """Check that the node is available in ComfyUI."""
    print("[TEST] Node registered... ", end="", flush=True)
    req = urllib.request.Request(f"{base_url}/object_info/Load%20Image%20Batch")
    try:
        with urllib.request.urlopen(req) as resp:
            info = json.loads(resp.read())
        if "Load Image Batch" in info:
            print("PASS")
            return True
        else:
            print(f"FAIL — node not found in response")
            return False
    except urllib.error.HTTPError as e:
        print(f"FAIL — {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="E2E tests for comfyui-batch-ops")
    parser.add_argument("--comfyui-url", default="http://127.0.0.1:8188")
    parser.add_argument("--image-dir", required=True, help="Directory with test images")
    args = parser.parse_args()

    # Normalize path
    image_dir = os.path.abspath(args.image_dir)
    if not os.path.isdir(image_dir):
        print(f"Error: {image_dir} is not a directory")
        sys.exit(1)

    # Check ComfyUI is reachable
    try:
        urllib.request.urlopen(f"{args.comfyui_url}/system_stats")
    except urllib.error.URLError:
        print(f"Error: Cannot reach ComfyUI at {args.comfyui_url}")
        sys.exit(1)

    results = [
        test_node_registered(args.comfyui_url),
        test_index_mode(args.comfyui_url, image_dir),
        test_sequential_mode(args.comfyui_url, image_dir),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
