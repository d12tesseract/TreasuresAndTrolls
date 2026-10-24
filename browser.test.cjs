const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { pathToFileURL } = require("node:url");
const { spawn } = require("node:child_process");
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function until(action, description, timeout = 15000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
        const result = await action();
        if (result) return result;
        await delay(50);
    }
    throw new Error(`Timed out: ${description}`);
}

async function connect(url) {
    const socket = new WebSocket(url), pending = new Map(), handlers = new Map();
    let sequence = 0;
    await new Promise((resolve, reject) => {
        socket.addEventListener("open", resolve, { once: true });
        socket.addEventListener("error", reject, { once: true });
    });
    socket.addEventListener("message", event => {
        const message = JSON.parse(event.data);
        if (message.id) {
            const request = pending.get(message.id);
            if (!request) return;
            clearTimeout(request.timer);
            pending.delete(message.id);
            if (message.error) request.reject(new Error(message.error.message));
            else request.resolve(message.result);
        } else if (handlers.has(message.method)) handlers.get(message.method)(message.params);
    });
    return {
        socket,
        on(method, handler) { handlers.set(method, handler); },
        call(method, params = {}) {
            const id = ++sequence;
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 30000);
                pending.set(id, { resolve, reject, timer });
                socket.send(JSON.stringify({ id, method, params }));
            });
        }
    };
}

test("offline browser painting, drafts, resize/move, ASCII files, scale, and native SVG downloads", { timeout: 180000 }, async t => {
    const executable = process.env.BROWSER || path.join(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)",
        "Microsoft", "Edge", "Application", "msedge.exe");
    await fs.access(executable);
    const profile = await fs.mkdtemp(path.join(os.tmpdir(), "dungeon-editor-browser-"));
    const downloads = path.join(profile, "downloads");
    await fs.mkdir(downloads);
    const editor = path.join(profile, "map_editor.html");
    await fs.copyFile(path.join(__dirname, "..", "map_editor.html"), editor);
    const child = spawn(executable, [
        "--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking", "--disable-extensions", "--remote-debugging-port=0",
        `--user-data-dir=${profile}`, "--window-size=1400,1000", "about:blank"
    ], { stdio: "ignore" });
    let browser, page;
    const pageErrors = [], requests = [], dialogErrors = [];
    let acceptDialog = true;
    try {
        const portFile = path.join(profile, "DevToolsActivePort");
        const port = await until(async () => {
            try { return (await fs.readFile(portFile, "utf8")).split("\n")[0]; }
            catch (error) { if (error.code === "ENOENT") return null; throw error; }
        }, "browser debugging port");
        const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
        browser = await connect(version.webSocketDebuggerUrl);
        await browser.call("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
        const target = await browser.call("Target.createTarget", { url: "about:blank" });
        const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
        page = await connect(targets.find(item => item.id === target.targetId).webSocketDebuggerUrl);
        page.on("Runtime.exceptionThrown", event => pageErrors.push(event.exceptionDetails));
        page.on("Network.requestWillBeSent", event => requests.push(event.request.url));
        page.on("Page.javascriptDialogOpening", () => {
            page.call("Page.handleJavaScriptDialog", { accept: acceptDialog }).catch(error => dialogErrors.push(error.message));
        });
        await page.call("Page.enable");
        await page.call("Runtime.enable");
        await page.call("Network.enable");
        await page.call("Network.emulateNetworkConditions", { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
        const evaluate = async expression => {
            const response = await page.call("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
            if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
            return response.result.value;
        };
        await page.call("Page.navigate", { url: pathToFileURL(editor).href });
        await until(() => evaluate("document.readyState === 'complete' && !!globalThis.DungeonEditor?.document"), "local editor startup");
        const settle = () => evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
        const click = async id => {
            await evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);
            await settle();
        };
        const input = (id, value, change = false) => evaluate(`(() => {
            const input = document.getElementById(${JSON.stringify(id)});
            input.value = ${JSON.stringify(String(value))};
            ${change ? 'input.dispatchEvent(new Event("change", {bubbles:true}));' : ""}
        })()`);
        const select = tile => evaluate(`document.querySelectorAll('#palette button').forEach(button => {
            if (button.dataset.tile === ${JSON.stringify(tile)}) button.click();
        })`);
        const point = (x, y) => evaluate(`(() => {
            const canvas = document.getElementById('map'), view = document.getElementById('viewport');
            const cellWidth = canvas.getBoundingClientRect().width / DungeonEditor.document.grid.width;
            const cellHeight = canvas.getBoundingClientRect().height / DungeonEditor.document.grid.height;
            view.scrollLeft = Math.max(0, ${x} * cellWidth - 100);
            view.scrollTop = Math.max(0, ${y} * cellHeight - 100);
            const rect = canvas.getBoundingClientRect();
            return {x: rect.left + (${x} + 0.5) * cellWidth, y: rect.top + (${y} + 0.5) * cellHeight};
        })()`);
        const mouse = async (type, point, pressed = false) => {
            await page.call("Input.dispatchMouseEvent", {
                type, ...point, button: type === "mouseMoved" && !pressed ? "none" : "left", buttons: pressed ? 1 : 0, clickCount: 1
            });
            await settle();
        };
        const paint = async (first, last = first) => {
            const start = await point(...first), end = await point(...last);
            await mouse("mouseMoved", start);
            await mouse("mousePressed", start, true);
            await mouse("mouseMoved", end, true);
            await mouse("mouseReleased", end);
        };
        const load = async (name, text) => {
            const file = path.join(profile, name);
            await fs.writeFile(file, text, "utf8");
            const root = await page.call("DOM.getDocument");
            const node = await page.call("DOM.querySelector", { nodeId: root.root.nodeId, selector: "#load" });
            await page.call("DOM.setFileInputFiles", { nodeId: node.nodeId, files: [file] });
            await until(() => evaluate("document.getElementById('load').value === ''"), "ASCII import");
            await settle();
        };
        const tile = (x, y) => evaluate(`DungeonEditor.document.grid.tile(${x},${y})`);
        const ascii = () => evaluate("DungeonEditor.document.grid.toAscii()");
        const downloaded = name => until(async () => {
            try { return await fs.readFile(path.join(downloads, name), "utf8"); }
            catch (error) { if (error.code === "ENOENT") return null; throw error; }
        }, `download ${name}`);

        await input("width", 8); await input("height", 8); await click("resize");
        await evaluate(`globalThis.moveEvents = [];
            for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel', 'lostpointercapture']) {
                document.getElementById('map').addEventListener(type, event => moveEvents.push({
                    type, pointer: event.pointerId, buttons: event.buttons, stroke: !!DungeonEditor.document.stroke,
                    x: event.clientX, y: event.clientY,
                    rect: document.getElementById('map').getBoundingClientRect().toJSON()
                }));
            }`);
        await select(" "); await paint([1, 1], [5, 1]);
        assert.equal(await tile(4, 1), " ", JSON.stringify(await evaluate(`({
            events: moveEvents, ascii: DungeonEditor.document.grid.toAscii(),
            status: document.getElementById('status').textContent
        })`)));
        await click("undo");
        assert.equal(await tile(4, 1), "#");
        await click("redo");
        assert.equal(await tile(4, 1), " ");
        await page.call("Input.dispatchKeyEvent", { type: "keyDown", key: "z", code: "KeyZ", modifiers: 2 });
        await page.call("Input.dispatchKeyEvent", { type: "keyUp", key: "z", code: "KeyZ", modifiers: 2 });
        assert.equal(await tile(4, 1), "#");
        await click("redo");
        await input("brush", 3); await paint([0, 0]);
        assert.equal(await tile(0, 1), " ");
        assert.equal(await tile(2, 0), "#");
        await click("undo");
        const beforeZoom = await ascii();
        const historyBeforeZoom = await evaluate("DungeonEditor.document.undoStack.length");
        await input("zoom", 2, true);
        assert.equal(await evaluate("document.getElementById('map').getBoundingClientRect().width"), 320);
        assert.equal(await ascii(), beforeZoom);
        assert.equal(await evaluate("DungeonEditor.document.undoStack.length"), historyBeforeZoom);
        await input("brush", 2, true);
        await evaluate(`(() => {
            globalThis.brushPreview = null;
            const context = document.getElementById('map').getContext('2d'), strokeRect = context.strokeRect;
            context.strokeRect = function(...args) {
                if (this.strokeStyle === '#1262a8') brushPreview = args;
                return strokeRect.apply(this, args);
            };
        })()`);
        await mouse("mouseMoved", await point(2, 3));
        assert.deepEqual(await evaluate("brushPreview"), [40, 60, 40, 40]);
        await paint([2, 3]);
        for (const [x, y] of [[2, 3], [3, 3], [2, 4], [3, 4]]) assert.equal(await tile(x, y), " ");
        assert.equal(await tile(1, 3), "#");
        assert.equal(await tile(4, 3), "#");
        await click("undo");
        assert.equal(await ascii(), beforeZoom);
        await click("zoom-out");
        assert.equal(await evaluate("document.getElementById('zoom').value"), "1.5");
        await input("zoom", 0.5, true);
        await paint([7, 7]);
        assert.equal(await tile(7, 7), " ");
        assert.equal(await tile(6, 7), "#");
        await click("undo");
        assert.equal(await ascii(), beforeZoom);
        await input("zoom", 0.25, true);
        assert.equal(await evaluate("document.getElementById('zoom-out').disabled"), true);
        await click("zoom-in");
        assert.equal(await evaluate("document.getElementById('zoom').value"), "0.5");
        await input("zoom", 4, true);
        assert.equal(await evaluate("document.getElementById('zoom-in').disabled"), true);
        await click("zoom-out");
        assert.equal(await evaluate("document.getElementById('zoom').value"), "3");
        await input("zoom", 1.5, true);
        await input("brush", 1); await select("/"); await paint([6, 6]);
        assert.equal(await tile(6, 6), "#");
        assert.match(await evaluate("document.getElementById('status').textContent"), /Diagonal needs/);

        await load("draft.txt", "########\n# b  C##\n#......#\n########\n");
        assert.equal(await tile(2, 1), "b");
        assert.equal(await evaluate("document.getElementById('save-svg').disabled"), true);
        await click("save-ascii");
        assert.match(await downloaded("draft.txt"), /# b  C##/);
        await select("b"); await paint([3, 1]);
        assert.equal(await evaluate("document.getElementById('save-svg').disabled"), false);
        const finished = await ascii();
        await load("invalid.txt", "dd\nd#\n");
        assert.equal(await ascii(), finished);
        assert.match(await evaluate("document.getElementById('status').textContent"), /straight horizontal or vertical/);

        await click("move-tool");
        await paint([0, 0], [1, 1]);
        assert.equal(await tile(3, 2), "b", JSON.stringify(await evaluate(`({
            events: moveEvents, ascii: DungeonEditor.document.grid.toAscii(),
            status: document.getElementById('status').textContent
        })`)));
        await click("undo");
        assert.equal(await ascii(), finished);
        const start = await point(0, 0), end = await point(1, 1);
        await mouse("mousePressed", start, true);
        await mouse("mouseMoved", end, true);
        await evaluate("document.getElementById('map').dispatchEvent(new PointerEvent('pointercancel'))");
        await mouse("mouseReleased", end);
        assert.equal(await ascii(), finished);
        await paint([0, 0], [4, 0]);
        assert.equal(await ascii(), finished);
        assert.match(await evaluate("document.getElementById('status').textContent"), /Expand the map first/);

        acceptDialog = false;
        await input("width", 4); await input("height", 3); await click("resize");
        await delay(100);
        assert.equal(await evaluate("DungeonEditor.document.grid.width"), 8);
        acceptDialog = true;
        await input("width", 4); await input("height", 3); await click("resize");
        await until(() => evaluate("DungeonEditor.document.grid.width === 4"), "confirmed shrink");
        await click("undo");
        assert.equal(await ascii(), finished);
        await input("width", 10); await input("height", 6); await click("resize");
        assert.equal(await tile(9, 5), "#");
        await click("undo");

        await input("scale", 5, true);
        await input("filename", "finished");
        await click("save-svg");
        const svg = await downloaded("finished.svg");
        assert.match(svg, /width="0.81in"/);
        assert.equal((svg.match(/data-tile="b"/g) || []).length, 1);
        assert.match(svg, /x1="0" y1="0.5" x2="0.5" y2="0.5"/);
        assert.match(svg, /x1="1.5" y1="0.5" x2="2" y2="0.5"/);
        assert.match(svg, /data-tile="C"/);
        await click("save-ascii");
        assert.equal(await downloaded("finished.txt"), finished);
        await input("scale", 0, true);
        assert.equal(await evaluate("DungeonEditor.document.feetPerSquare"), 5);
        assert.match(await evaluate("document.getElementById('status').textContent"), /greater than zero/);

        await evaluate(`globalThis.labelDraws = [];
            const context = document.getElementById('map').getContext('2d'), fillText = context.fillText;
            context.fillText = function(text, ...args) {
                labelDraws.push(text);
                return fillText.call(this, text, ...args);
            };`);
        await load("labels.txt", "####\n# T#\n####\n\n0,0: Stone\n2,1: 7\n");
        assert.ok((await evaluate("labelDraws")).includes("Stone"));
        const rightClick = async (x, y) => {
            const location = await point(x, y);
            await page.call("Input.dispatchMouseEvent", { type: "mousePressed", ...location,
                button: "right", buttons: 2, clickCount: 1 });
            await page.call("Input.dispatchMouseEvent", { type: "mouseReleased", ...location,
                button: "right", buttons: 0, clickCount: 1 });
            await until(() => evaluate("document.getElementById('label-editor').open"), "right-click label editor");
        };
        await rightClick(0, 0);
        assert.equal(await evaluate("document.getElementById('label-text').value"), "Stone");
        await input("label-text", 'Rock: <&> \u00e9');
        await click("label-save");
        assert.equal(await tile(0, 0), "#");
        assert.match(await ascii(), /0,0: Rock: <&> \u00e9/);
        await click("undo");
        assert.match(await ascii(), /0,0: Stone/);
        await click("redo");
        await rightClick(1, 0);
        await input("label-text", "New note");
        await click("label-save");
        assert.match(await ascii(), /1,0: New note/);
        await rightClick(1, 0);
        await input("label-text", "Cancelled");
        await click("label-cancel");
        assert.match(await ascii(), /1,0: New note/);
        await rightClick(1, 0);
        await click("label-remove");
        assert.doesNotMatch(await ascii(), /1,0:/);
        await click("undo");
        assert.match(await ascii(), /1,0: New note/);
        await rightClick(1, 0);
        await input("label-text", "");
        await click("label-save");
        assert.doesNotMatch(await ascii(), /1,0:/);
        await evaluate("labelDraws.length = 0");
        await click("show-labels");
        assert.ok(!(await evaluate("labelDraws")).includes("Rock: <&> \u00e9"));
        await input("filename", "labels-hidden");
        await click("save-svg");
        assert.doesNotMatch(await downloaded("labels-hidden.svg"), /id="encounters"/);
        await input("filename", "labels");
        await click("save-ascii");
        assert.equal(await downloaded("labels.txt"), await ascii());
        await click("show-labels");
        assert.ok((await evaluate("labelDraws")).includes("Rock: <&> \u00e9"));
        await input("filename", "labels-visible");
        await click("save-svg");
        const labeledSvg = await downloaded("labels-visible.svg");
        assert.match(labeledSvg, /data-area="Rock: &lt;&amp;&gt; \u00e9"/);
        assert.match(labeledSvg, /transform="translate\(0 0\)"/);
        await input("zoom", 1, true);

        const dense = Array.from({ length: 128 }, (_, y) =>
            Array.from({ length: 128 }, (_, x) => (x + y) % 2 ? "." : "#").join("")).join("\n") + "\n";
        await load("large.txt", dense);
        await evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
        const performance = await evaluate(`(() => {
            const start = performance.now();
            const svg = DungeonEditor.renderSvg(DungeonEditor.document.grid);
            return {milliseconds: performance.now() - start, bytes: svg.length, width: document.getElementById('map').width};
        })()`);
        assert.ok(performance.bytes > 1000);
        assert.ok(performance.width >= 2560);
        t.diagnostic(`128x128 dense rough SVG: ${Math.round(performance.milliseconds)} ms, ${performance.bytes} characters.`);
        await load("wide.txt", ("#".repeat(256) + "\n").repeat(64));
        await input("zoom", 2, true);
        const backingWidth = await evaluate("document.getElementById('map').width");
        await evaluate("document.getElementById('viewport').scrollLeft = 1000; document.getElementById('viewport').scrollTop = 400");
        const scrollCenter = () => evaluate(`(() => {
            const view = document.getElementById('viewport'), rect = document.getElementById('map').getBoundingClientRect();
            return [(view.scrollLeft + view.clientWidth / 2) * DungeonEditor.document.grid.width / rect.width,
                (view.scrollTop + view.clientHeight / 2) * DungeonEditor.document.grid.height / rect.height];
        })()`);
        const centerBeforeZoom = await scrollCenter();
        await input("zoom", 4, true);
        assert.equal(await evaluate("document.getElementById('map').width"), backingWidth);
        assert.equal(await evaluate("document.getElementById('map').getBoundingClientRect().width"), 20480);
        const centerAfterZoom = await scrollCenter();
        for (let axis = 0; axis < 2; axis++) assert.ok(Math.abs(centerBeforeZoom[axis] - centerAfterZoom[axis]) < 0.05);
        await select(" "); await paint([250, 30]);
        assert.equal(await tile(250, 30), " ");
        assert.equal(await tile(249, 30), "#");
        await click("undo");
        assert.equal(await tile(250, 30), "#");

        await input("zoom", 1, true);
        await input("brush", 1, true);
        for (const door of "dxc") {
            for (const horizontal of [true, false]) {
                const name = `door-${door}-${horizontal ? "horizontal" : "vertical"}`;
                await load(`${name}.txt`, ("#".repeat(7) + "\n").repeat(7));
                await select(door);
                for (const step of [2, 3, 4]) {
                    await paint(horizontal ? [step, 3] : [3, step]);
                    assert.equal(await tile(...(horizontal ? [step, 3] : [3, step])), door);
                    assert.equal(await evaluate("document.getElementById('save-svg').disabled"), false);
                }
                if (horizontal) assert.equal((await ascii()).split("\n")[3], `##${door.repeat(3)}##`);
                await click("save-svg");
                const exported = await downloaded(`${name}.svg`);
                assert.equal((exported.match(new RegExp(`data-tile="${door}"`, "g")) || []).length, 1);
                assert.match(exported, /width="2.7" height="0.24"/);
                assert.match(exported, /x1="2.85" y1="0.5" x2="3" y2="0.5"/);
                assert.equal(exported.includes("rotate(90 .5 .5)"), !horizontal);
            }
        }
        for (const stair of "Ff") {
            const name = stair === "f" ? "stairs-down" : "stairs-up";
            await load(`${name}.txt`, (stair.repeat(4) + "\n").repeat(2));
            await click("save-svg");
            const exported = await downloaded(`${name}.svg`);
            const feature = exported.slice(exported.indexOf('<g id="features"'));
            assert.doesNotMatch(feature, /<text\b/);
            const treads = [...feature.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"/g)]
                .slice(0, 20).reverse().map(match => Number(match[3]) - Number(match[1]));
            assert.equal(treads.length, 20);
            assert.ok(Math.abs(treads[0] - 1.7) < 1e-9);
            assert.ok(Math.abs(treads.at(-1) / treads[0] - (stair === "f" ? 0.5 : 1)) < 1e-9);
            treads.slice(1).forEach((width, index) => {
                if (stair === "f") assert.ok(width < treads[index]);
                else assert.equal(width, treads[index]);
            });
            assert.match(feature, /x1="1" y1="3.82" x2="1" y2="0.18"/);
        }
        for (const tile of "Ss") {
            const name = tile === "s" ? "spiral-down" : "spiral-up";
            await load(`${name}.txt`, `#####\n# ${tile}${tile}#\n#${tile}#${tile}#\n#${tile.repeat(3)}#\n#####\n`);
            await click("save-svg");
            const exported = await downloaded(`${name}.svg`);
            const spiral = await evaluate(`(() => {
                const svg = new DOMParser().parseFromString(${JSON.stringify(exported)}, 'image/svg+xml').documentElement;
                svg.setAttribute('visibility', 'hidden');
                document.body.append(svg);
                try {
                    const drawing = svg.querySelector('[data-spiral="true"] > g');
                    const treads = [...drawing.querySelectorAll('line')].slice(0, -2);
                    const arrow = drawing.querySelector('path[data-direction]');
                    return {widths: treads.map(line => line.getTotalLength()),
                        direction: arrow.getAttribute('data-direction'), path: arrow.getAttribute('d')};
                } finally { svg.remove(); }
            })()`);
            assert.equal(spiral.direction, tile === "s" ? "down" : "up");
            assert.match(spiral.path, / A 1.125 1.125 /);
            assert.ok(Math.abs(spiral.widths[0] - 1) < 1e-6);
            assert.ok(Math.abs(spiral.widths.at(-1) - (tile === "s" ? 0.5 : 1)) < 1e-6);
            spiral.widths.slice(1).forEach((width, index) => {
                if (tile === "s") assert.ok(width < spiral.widths[index]);
                else assert.ok(Math.abs(width - spiral.widths[index]) < 1e-6);
            });
        }
        for (const [tile, name, length] of [["P", "ramp-up", 4], ["p", "ramp-down", 1]]) {
            await load(`${name}.txt`, tile.repeat(length) + "\n");
            await click("save-svg");
            const exported = await downloaded(`${name}.svg`);
            const annotation = await evaluate(`(() => {
                const svg = new DOMParser().parseFromString(${JSON.stringify(exported)}, 'image/svg+xml').documentElement;
                svg.setAttribute('visibility', 'hidden');
                document.body.append(svg);
                try {
                    const text = [...svg.querySelectorAll('text')].find(node => node.textContent.startsWith('ramp '));
                    return {text: text.textContent, width: text.getBBox().width,
                        fontSize: text.getAttribute('font-size'), textCount: svg.querySelectorAll('text').length};
                } finally { svg.remove(); }
            })()`);
            assert.equal(annotation.text, name.replace("-", " "));
            assert.equal(annotation.textCount, 1);
            assert.equal(annotation.fontSize, "0.9");
            assert.ok(annotation.width > 0 && annotation.width <= length - 0.4, JSON.stringify({annotation, length}));
        }
        await load("cavern-curves.txt", "##########\n#  ......#\n#  .##...#\n#  ......#\n##########\n");
        assert.equal(await evaluate("document.getElementById('wall-deviation').value"), "50");
        await input("wall-deviation", 51);
        await click("save-svg");
        assert.match(await evaluate("document.getElementById('status').textContent"), /deviation.*0%.*50%/i);
        for (const percentage of [50, 5, 0]) {
            await input("wall-deviation", percentage);
            await input("filename", `cavern-curves-${percentage}`);
            await click("save-svg");
            const cavernSvg = await downloaded(`cavern-curves-${percentage}.svg`);
            const cavern = await evaluate(`(() => {
            const svg = new DOMParser().parseFromString(${JSON.stringify(cavernSvg)}, 'image/svg+xml').documentElement;
            const edges = DungeonEditor.wallEdges(DungeonEditor.document.grid).filter(edge => edge.rough);
            const paths = [...svg.querySelectorAll('#walls path[data-texture="rough"]')];
            let deviation = 0;
            for (const path of paths) {
                const length = path.getTotalLength();
                for (let index = 0; index <= 80; index++) {
                    const point = path.getPointAtLength(length * index / 80);
                    let nearest = Infinity;
                    for (const {start, end} of edges) {
                        const dx = end[0] - start[0], dy = end[1] - start[1];
                        const t = Math.max(0, Math.min(1, ((point.x - start[0]) * dx +
                            (point.y - start[1]) * dy) / (dx * dx + dy * dy)));
                        nearest = Math.min(nearest, Math.hypot(point.x - start[0] - t * dx,
                            point.y - start[1] - t * dy));
                    }
                    deviation = Math.max(deviation, nearest);
                }
            }
            return {paths: paths.length, curves: paths.every(path => path.getAttribute('d').includes(' C ')),
                roughLines: svg.querySelectorAll('#walls line[data-texture="rough"]').length, deviation,
                smoothLines: svg.querySelectorAll('#walls line[data-texture="smooth"]').length,
                edges: DungeonEditor.wallEdges(DungeonEditor.document.grid).length};
            })()`);
            assert.equal(cavern.roughLines, 0);
            if (percentage === 0) {
                assert.equal(cavern.paths, 0);
                assert.equal(cavern.smoothLines, cavern.edges);
            } else {
                assert.ok(cavern.paths >= 2);
                assert.equal(cavern.curves, true);
                assert.ok(cavern.deviation <= percentage / 100 + 0.00001, JSON.stringify(cavern));
            }
        }
        await load("void.txt", "~\n");
        assert.deepEqual(await evaluate(`Array.from(document.getElementById('map').getContext('2d')
            .getImageData(10, 10, 1, 1).data)`), [48, 16, 79, 255]);
        await input("width", 512); await input("height", 512); await click("resize");
        assert.deepEqual(await evaluate(`[
            DungeonEditor.document.grid.width, DungeonEditor.document.grid.height,
            document.getElementById('width').max, document.getElementById('height').max
        ]`), [512, 512, "512", "512"]);
        await input("brush", 1, true);
        await select(" "); await paint([511, 511]);
        assert.equal(await tile(511, 511), " ");
        const maximumAscii = await ascii();
        await input("filename", "maximum");
        await click("save-ascii");
        assert.equal(await downloaded("maximum.txt"), maximumAscii);
        await load("maximum-roundtrip.txt", maximumAscii);
        assert.equal(await tile(511, 511), " ");
        await input("filename", "maximum");
        await input("scale", 10, true);
        await click("save-svg");
        assert.match(await downloaded("maximum.svg"), /512\.05 512\.05/);
        await click("zoom-in");
        assert.ok(await evaluate("document.getElementById('map').width <= 8192"));

        assert.deepEqual(pageErrors, []);
        assert.deepEqual(dialogErrors, []);
        assert.deepEqual(requests.filter(url => /^https?:/.test(url)), []);
        assert.deepEqual(requests.filter(url => /^file:/.test(url)), [pathToFileURL(editor).href]);
        await evaluate("DungeonEditor.document.markSaved()");
    } finally {
        if (browser) {
            await browser.call("Browser.close");
            browser.socket.close();
        } else child.kill();
        if (page) page.socket.close();
        if (child.exitCode === null) await Promise.race([
            new Promise(resolve => child.once("exit", resolve)), delay(8000)
        ]);
        if (child.exitCode === null) child.kill();
        await fs.rm(profile, { recursive: true, force: true, maxRetries: 20, retryDelay: 100 });
    }
});
