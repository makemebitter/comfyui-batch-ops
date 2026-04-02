import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

// Update widget values from server feedback (mirrors sequential index)
api.addEventListener("batch-ops-node-feedback", (event) => {
    const { node_id, widget_name, value } = event.detail;
    // LiteGraph _nodes_by_id may use int or string keys — try both
    const node = app.graph._nodes_by_id[node_id] || app.graph._nodes_by_id[parseInt(node_id)];
    if (node) {
        const widget = node.widgets.find((w) => w.name === widget_name);
        if (widget) {
            widget.value = value;
            app.graph.setDirtyCanvas(true);
        }
    }
});

// Re-queue prompt when server requests it
api.addEventListener("batch-ops-add-queue", () => {
    app.queuePrompt(0, 1);
});

// Make index widget read-only — it's display-only, driven by server state
app.registerExtension({
    name: "BatchOps.LoadImageBatch",
    nodeCreated(node) {
        if (node.comfyClass !== "BatchOps_LoadImageBatch") return;

        const indexWidget = node.widgets.find((w) => w.name === "index");
        if (indexWidget) {
            // Override mouse handler to prevent user interaction
            indexWidget.mouse = function () { return false; };
            // Override the draw method to show grayed out
            const origDraw = indexWidget.draw;
            if (origDraw) {
                indexWidget.draw = function (ctx, node, width, y, height) {
                    const prevAlpha = ctx.globalAlpha;
                    ctx.globalAlpha = 0.5;
                    origDraw.call(this, ctx, node, width, y, height);
                    ctx.globalAlpha = prevAlpha;
                };
            }
        }
    },
});
