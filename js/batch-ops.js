import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";

// Update widget values from server feedback (mirrors progress)
api.addEventListener("batch-ops-node-feedback", (event) => {
    const { node_id, widget_name, value } = event.detail;
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

// Make progress widget read-only
app.registerExtension({
    name: "BatchOps.LoadImageBatch",
    nodeCreated(node) {
        if (node.comfyClass !== "BatchOps_LoadImageBatch") return;

        const progressWidget = node.widgets.find((w) => w.name === "progress");
        if (progressWidget) {
            progressWidget.mouse = function () { return false; };
            const origDraw = progressWidget.draw;
            if (origDraw) {
                progressWidget.draw = function (ctx, node, width, y, height) {
                    const prevAlpha = ctx.globalAlpha;
                    ctx.globalAlpha = 0.5;
                    origDraw.call(this, ctx, node, width, y, height);
                    ctx.globalAlpha = prevAlpha;
                };
            }
        }
    },
});
