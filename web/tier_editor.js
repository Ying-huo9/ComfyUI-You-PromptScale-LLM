// PromptScale 扩写器 — 档位指令编辑(方案3 改进版)
// 三个档位指令 widget 在节点上隐藏,widget 值 = 唯一事实源(随工作流序列化);
// properties 里只放短摘要(前24字+字数),属性面板因此排版干净;
// 在属性面板改摘要 = 整体替换该档指令;右键「编辑档位指令」编辑全文,两处实时同步。
// 清空任一指令 = 运行时回退插件内置指令。

import { app } from "../../scripts/app.js";

const TIER_WIDGETS = ["SFW指令", "Suggestive指令", "NSFW指令"];
const LEGACY_PREFIX = "档位指令·"; // 旧版把全文镜像进 properties 的键,加载时清除

function findWidget(node, name) {
    return (node.widgets || []).find((w) => w.name === name) || null;
}

function hideWidget(node, widget) {
    // converted-widget 技巧:不参与布局、不渲染,但序列化照常
    widget.type = "converted-widget";
    widget.computeSize = () => [0, -4];
    widget.hidden = true;
    if (widget.onRemove) widget.onRemove();
}

function summarize(text) {
    const v = String(text ?? "").replace(/\s+/g, " ").trim();
    if (!v) return "（内置默认）";
    const n = String(text ?? "").length;
    return v.length > 24 ? v.slice(0, 24) + `… (${n}字)` : `${v} (${n}字)`;
}

// widget → properties(写摘要)
function widgetToProp(node, name) {
    const w = findWidget(node, name);
    if (!w) return;
    node.properties[name] = summarize(w.value);
}

function purgeLegacyProps(node) {
    for (const key of Object.keys(node.properties || {})) {
        if (key.startsWith(LEGACY_PREFIX)) delete node.properties[key];
    }
}

function openTierEditor(node) {
    // 简易模态:3 个多行文本框,保存时同步 widget 与 properties 摘要
    const overlay = document.createElement("div");
    overlay.style.cssText = [
        "position:fixed", "inset:0", "z-index:99999",
        "background:rgba(0,0,0,0.45)",
        "display:flex", "align-items:center", "justify-content:center",
    ].join(";");

    const box = document.createElement("div");
    box.style.cssText = [
        "background:var(--comfy-menu-bg, #2a2a2a)", "color:var(--input-text, #ddd)",
        "border:1px solid var(--border-color, #555)", "border-radius:8px",
        "padding:16px", "width:min(760px, 92vw)", "max-height:88vh",
        "overflow:auto", "font-size:13px", "box-shadow:0 8px 30px rgba(0,0,0,0.5)",
    ].join(";");

    const title = document.createElement("div");
    title.textContent = "编辑档位指令（清空 = 回退内置指令；选 Auto 档时不追加任何指令）";
    title.style.cssText = "font-weight:600;margin-bottom:10px;";
    box.appendChild(title);

    const inputs = {};
    for (const name of TIER_WIDGETS) {
        const label = document.createElement("div");
        label.textContent = name + "　（" + (
            name === "SFW指令" ? "保守/衣着完整" :
            name === "Suggestive指令" ? "擦边/性感氛围" : "直接描写") + "）";
        label.style.cssText = "margin:10px 0 4px;font-weight:600;";
        box.appendChild(label);

        const ta = document.createElement("textarea");
        ta.value = findWidget(node, name)?.value ?? "";
        ta.rows = name === "SFW指令" ? 5 : 6;
        ta.style.cssText = [
            "width:100%", "box-sizing:border-box", "resize:vertical",
            "background:var(--comfy-input-bg, #333)", "color:var(--input-text, #ddd)",
            "border:1px solid var(--border-color, #555)", "border-radius:4px",
            "padding:6px", "font-size:12px", "line-height:1.5",
        ].join(";");
        box.appendChild(ta);
        inputs[name] = ta;
    }

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "margin-top:14px;display:flex;gap:10px;justify-content:flex-end;";
    const mkBtn = (text, fn, primary) => {
        const b = document.createElement("button");
        b.textContent = text;
        b.style.cssText = [
            "padding:6px 18px", "border-radius:4px", "cursor:pointer",
            primary ? "background:#3a7ca5;color:#fff;border:none;"
                    : "background:transparent;color:inherit;border:1px solid var(--border-color,#555)",
        ].join("");
        b.onclick = fn;
        return b;
    };
    btnRow.appendChild(mkBtn("取消", () => overlay.remove(), false));
    btnRow.appendChild(mkBtn("保存", () => {
        for (const name of TIER_WIDGETS) {
            const w = findWidget(node, name);
            if (w) w.value = inputs[name].value;
            widgetToProp(node, name);
        }
        app.graph?.change?.();
        overlay.remove();
    }, true));
    box.appendChild(btnRow);

    overlay.appendChild(box);
    document.body.appendChild(overlay);
}

app.registerExtension({
    name: "PromptScale.TierEditor",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "PSEnhancer") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = origOnNodeCreated?.apply(this, arguments);

            purgeLegacyProps(this);

            // 隐藏三个档位 widget,properties 只放短摘要
            for (const name of TIER_WIDGETS) {
                const w = findWidget(this, name);
                if (w) {
                    hideWidget(this, w);
                    widgetToProp(this, name);
                }
            }

            // 属性面板改动 = 整体替换该档指令;随后把显示刷回短摘要
            const origOnPropChanged = this.onPropertyChanged;
            this.onPropertyChanged = function (name, value) {
                if (TIER_WIDGETS.includes(name) && typeof value === "string") {
                    const w = findWidget(this, name);
                    if (w) w.value = value;
                    widgetToProp(this, name);
                }
                return origOnPropChanged?.apply(this, arguments);
            };

            // 工作流加载(configure)后:widget 值为事实源,刷新摘要并清理旧版全文键
            const origOnConfigure = this.onConfigure;
            this.onConfigure = function () {
                const r2 = origOnConfigure?.apply(this, arguments);
                purgeLegacyProps(this);
                for (const name of TIER_WIDGETS) widgetToProp(this, name);
                return r2;
            };

            // 保存前兜底:properties 摘要与 widget 保持一致
            const origOnSerialize = this.onSerialize;
            this.onSerialize = function (o) {
                for (const name of TIER_WIDGETS) widgetToProp(this, name);
                return origOnSerialize?.apply(this, arguments);
            };

            // 右键菜单:大编辑框入口
            const origExtra = this.getExtraMenuOptions;
            this.getExtraMenuOptions = function (canvas, options) {
                const r3 = origExtra?.apply(this, arguments);
                options.unshift({
                    content: "编辑档位指令",
                    callback: () => openTierEditor(this),
                });
                return r3 ?? options;
            };

            return r;
        };
    },
});
