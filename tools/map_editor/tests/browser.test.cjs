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
            view.scrollLeft = Math.max(0, ${x} * 20 - 100);
            view.scrollTop = Math.max(0, ${y} * 20 - 100);
            const rect = canvas.getBoundingClientRect();
            return {x: rect.left + ${x} * 20 + 10, y: rect.top + ${y} * 20 + 10};
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
        await input("brush", 1); await select("d"); await paint([6, 6]);
        assert.equal(await tile(6, 6), "#");
        assert.match(await evaluate("document.getElementById('status').textContent"), /Door needs/);

        await load("draft.txt", "########\n# b  C##\n#......#\n########\n");
        assert.equal(await tile(2, 1), "b");
        assert.equal(await evaluate("document.getElementById('save-svg').disabled"), true);
        await click("save-ascii");
        assert.match(await downloaded("draft.txt"), /# b  C##/);
        await select("b"); await paint([3, 1]);
        assert.equal(await evaluate("document.getElementById('save-svg').disabled"), false);
        const finished = await ascii();
        await load("invalid.txt", "#d#\n");
        assert.equal(await ascii(), finished);
        assert.match(await evaluate("document.getElementById('status').textContent"), /Door needs/);

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
