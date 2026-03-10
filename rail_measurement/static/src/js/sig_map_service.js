/** @odoo-module **/

const sigMapService = {
    start(env) {
        let floatEl = null;

        function open(sigControllerId, measurementId) {
            if (floatEl) floatEl.remove();

            floatEl = document.createElement("div");
            floatEl.id = "sig-float-root";
            document.body.appendChild(floatEl);

            floatEl.innerHTML = `
                <div id="sig-float-window" style="
                    position:fixed;z-index:9999;
                    right:20px;top:60px;
                    width:480px;
                    height:520px;
                    box-shadow:0 8px 32px rgba(0,0,0,0.25);
                    border-radius:10px;overflow:hidden;
                    background:#fff;border:1px solid #e2e8f0;
                    resize:both;
                    display:flex;
                    flex-direction:column;
                ">
                    <div id="sig-float-bar" style="
                        display:flex;align-items:center;justify-content:space-between;
                        padding:6px 10px;background:#1e293b;cursor:grab;user-select:none;
                        flex-shrink:0;
                    ">
                        <span style="color:#fff;font-size:12px;font-weight:600;">🗺️ LEYFA SIG</span>
                        <span style="display:flex;gap:6px;">
                            <button id="sig-btn-refresh"
                                style="border:none;background:#1a56db;color:#fff;
                                       border-radius:4px;padding:1px 8px;cursor:pointer;font-size:13px;"
                                title="Rafraîchir">↺</button>
                            <button id="sig-btn-save"
                                style="border:none;background:#475569;color:#fff;
                                    border-radius:4px;padding:1px 8px;cursor:pointer;font-size:13px;"
                                title="PNG">💾</button>
                            <div id="sig-save-menu" style="
                                display:none;
                                position:absolute;
                                top:34px;right:40px;
                                background:#fff;
                                border:1px solid #e2e8f0;
                                border-radius:6px;
                                box-shadow:0 4px 16px rgba(0,0,0,0.15);
                                z-index:10000;
                                min-width:160px;
                                overflow:hidden;
                            "></div>
                            <button id="sig-btn-close"
                                style="border:none;background:#dc2626;color:#fff;
                                       border-radius:4px;padding:1px 8px;cursor:pointer;font-size:13px;">✕</button>
                        </span>
                    </div>
                    <div id="sig-float-body" style="
                        flex:1;
                        min-height:0;
                        overflow:hidden;
                    ">
                        <iframe
                            id="sig-iframe"
                            src="/leyfa/sig/map/${sigControllerId}"
                            style="width:100%;height:100%;border:none;"
                        ></iframe>
                    </div>
                </div>
            `;
            // ── PNG save dropdown ─────────────────────────────────────────────────
            const btnSave = floatEl.querySelector("#sig-btn-save");
            const saveMenu = floatEl.querySelector("#sig-save-menu");

            function buildSaveMenu() {
                fetch('/web/dataset/call_kw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {
                            model:  'leyfa.sig.controller',
                            method: 'read',
                            args:   [[sigControllerId], ['map_png']],
                            kwargs: {}
                        }
                    })
                }).then(r => r.json()).then(data => {
                    const hasPng = !!(data.result && data.result[0] && data.result[0].map_png);
                    const itemStyle = "padding:7px 14px;cursor:pointer;font-size:12px;color:#1e293b;white-space:nowrap;";

                    let html = '';
                    if (hasPng) {
                        html += `<div class="sig-menu-item" data-action="view" style="${itemStyle}">🖼️ Voir le PNG</div>`;
                    }
                    html += `<div class="sig-menu-item" data-action="save" style="${itemStyle}">💾 Sauvegarder PNG</div>`;
                    if (hasPng) {
                        html += `<div class="sig-menu-item" data-action="remove" style="${itemStyle};color:#dc2626;">🗑️ Supprimer PNG</div>`;
                    }

                    saveMenu.innerHTML = html;
                    saveMenu.style.display = 'block';

                    saveMenu.querySelectorAll('.sig-menu-item').forEach(item => {
                        item.addEventListener('mouseenter', () => item.style.background = '#f1f5f9');
                        item.addEventListener('mouseleave', () => item.style.background = '');
                        item.addEventListener('click', () => {
                            saveMenu.style.display = 'none';
                            const action = item.dataset.action;
                            if (action === 'save')        doSavePng();
                            else if (action === 'view')   doViewPng();
                            else if (action === 'remove') doRemovePng();
                        });
                    });
                });
            }

            btnSave.addEventListener('click', (e) => {
                e.stopPropagation();
                if (saveMenu.style.display === 'none' || !saveMenu.style.display) {
                    buildSaveMenu();
                } else {
                    saveMenu.style.display = 'none';
                }
            });

            document.addEventListener('click', () => { saveMenu.style.display = 'none'; });

            // ── Refresh ───────────────────────────────────────────────────────────
            floatEl.querySelector("#sig-btn-refresh").addEventListener("click", doRefresh);

            // ── Close ─────────────────────────────────────────────────────────────
            floatEl.querySelector("#sig-btn-close").addEventListener("click", () => {
                floatEl.remove();
                floatEl = null;
            });

            // ── Drag ──────────────────────────────────────────────────────────────
            const win = floatEl.querySelector("#sig-float-window");
            const bar = floatEl.querySelector("#sig-float-bar");
            let dragging = false, ox = 0, oy = 0;

            bar.addEventListener("mousedown", e => {
                dragging = true;
                ox = e.clientX - win.getBoundingClientRect().left;
                oy = e.clientY - win.getBoundingClientRect().top;
                e.preventDefault();
            });
            document.addEventListener("mousemove", e => {
                if (!dragging) return;
                win.style.left  = (e.clientX - ox) + "px";
                win.style.top   = (e.clientY - oy) + "px";
                win.style.right = "auto";
            });
            document.addEventListener("mouseup", () => { dragging = false; });

            // ── PNG actions ───────────────────────────────────────────────────────
            async function doSavePng() {
                btnSave.textContent = '⏳';
                btnSave.disabled = true;
                try {
                    const iframe = floatEl.querySelector("#sig-iframe");
                    const canvas = await iframe.contentWindow.buildMapCanvas();
                    canvas.toBlob(blob => {
                        const reader = new FileReader();
                        reader.onloadend = () => {
                            const b64 = reader.result.split(',')[1];
                            fetch('/web/dataset/call_kw', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({
                                    jsonrpc: '2.0', method: 'call', id: 1,
                                    params: {
                                        model:  'leyfa.sig.controller',
                                        method: 'save_png',
                                        args:   [[sigControllerId], b64],
                                        kwargs: {}
                                    }
                                })
                            }).then(() => {
                                btnSave.textContent = '✅';
                                setTimeout(() => {
                                    btnSave.textContent = '💾';
                                    btnSave.disabled = false;
                                }, 1500);
                            });
                        };
                        reader.readAsDataURL(blob);
                    }, 'image/png');
                } catch(e) {
                    console.warn('doSavePng failed:', e);
                    btnSave.textContent = '💾';
                    btnSave.disabled = false;
                }
            }

            function doViewPng() {
                fetch('/web/dataset/call_kw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {
                            model:  'leyfa.sig.controller',
                            method: 'read',
                            args:   [[sigControllerId], ['map_png']],
                            kwargs: {}
                        }
                    })
                }).then(r => r.json()).then(data => {
                    const b64 = data.result && data.result[0] && data.result[0].map_png;
                    if (!b64) return;
                    const w = window.open();
                    w.document.write('<img src="data:image/png;base64,' + b64 + '" style="max-width:100%"/>');
                });
            }

            function doRemovePng() {
                fetch('/web/dataset/call_kw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {
                            model:  'leyfa.sig.controller',
                            method: 'write',
                            args:   [[sigControllerId], {map_png: false}],
                            kwargs: {}
                        }
                    })
                }).then(() => {
                    btnSave.textContent = '💾';
                });
            }

            // ── Refresh helper ────────────────────────────────────────────────────
            function doRefresh() {
                const iframe = floatEl.querySelector("#sig-iframe");
                if (!iframe) return;
                iframe.style.opacity = "0.4";
                fetch('/web/dataset/call_kw', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        jsonrpc: '2.0', method: 'call', id: 1,
                        params: {
                            model:  'rail.measurement',
                            method: 'action_refresh_sig',
                            args:   [[measurementId]],
                            kwargs: {}
                        }
                    })
                }).then(() => {
                    iframe.src = `/leyfa/sig/map/${sigControllerId}?t=${Date.now()}`;
                    iframe.onload = () => { iframe.style.opacity = "1"; };
                });
            }
        }

        function close() {
            if (floatEl) { floatEl.remove(); floatEl = null; }
        }

        return { open, close };
    },
};

import { registry } from "@web/core/registry";
registry.category("services").add("sig_map", sigMapService);