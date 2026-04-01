import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

// Update widget values from server feedback (e.g. mirror sequential index)
api.addEventListener("batch-ops-node-feedback", (event) => {
    const { node_id, widget_name, value } = event.detail;
    const node = app.graph._nodes_by_id[node_id];
    if (node) {
        const widget = node.widgets.find((w) => w.name === widget_name);
        if (widget) {
            widget.value = value;
        }
    }
});

// Re-queue prompt when server requests it
api.addEventListener("batch-ops-add-queue", () => {
    app.queuePrompt(0, 1);
});

// Disable irrelevant widgets based on mode selection
app.registerExtension({
    name: "BatchOps.LoadImageBatch",
    nodeCreated(node) {
        if (node.comfyClass !== "BatchOps_LoadImageBatch") return;

        const modeWidget = node.widgets.find((w) => w.name === "mode");
        const indexWidget = node.widgets.find((w) => w.name === "index");
        const batchIdWidget = node.widgets.find((w) => w.name === "batch_id");
        const autoQueueWidget = node.widgets.find((w) => w.name === "auto_queue");

        if (!modeWidget) return;

        function updateWidgetStates() {
            const isIndex = modeWidget.value === "index";

            if (indexWidget) {
                indexWidget.disabled = !isIndex;
            }
            if (batchIdWidget) {
                batchIdWidget.disabled = isIndex;
            }
            if (autoQueueWidget) {
                autoQueueWidget.disabled = isIndex;
            }
        }

        // Run on creation
        updateWidgetStates();

        // Run on mode change
        const originalCallback = modeWidget.callback;
        modeWidget.callback = function (...args) {
            updateWidgetStates();
            if (originalCallback) {
                originalCallback.apply(this, args);
            }
        };
    },
});
