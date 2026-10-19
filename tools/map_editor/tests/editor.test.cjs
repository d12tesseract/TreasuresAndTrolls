const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createHash } = require("node:crypto");
const { spawnSync } = require("node:child_process");
const html = fs.readFileSync(path.join(__dirname, "..", "map_editor.html"), "utf8").replace(/\r\n?/g, "\n");
const core = html.match(/<script id="map-core">([\s\S]*?)<\/script>/);
assert.ok(core, "The standalone HTML must embed the map model, geometry, and renderer.");
vm.runInThisContext(core[1], { filename: "map_editor.html:map-core" });
const app = globalThis.DungeonEditor;
const fixtures = JSON.parse(fs.readFileSync(path.join(__dirname, "terrain-fixtures.json"), "utf8"));

test("the single HTML embeds all runtime assets with matching content-security hashes", () => {
    assert.doesNotMatch(html, /<script\b[^>]*\bsrc\s*=|<link\b[^>]*\brel=["']stylesheet/i);
    const policy = html.match(/http-equiv="Content-Security-Policy" content="([^"]+)"/)[1];
    const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)];
    const styles = [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)];
    assert.equal(scripts.length, 2);
    assert.equal(styles.length, 1);
    for (const [, content] of [...scripts, ...styles]) {
        const hash = createHash("sha256").update(content).digest("base64");
        assert.ok(policy.includes(`'sha256-${hash}'`), "Embedded content must match its CSP hash.");
    }
    assert.ok(policy.includes("connect-src 'none'"));
});

test("shared terrain fixtures match strict and editor-draft validation", () => {
    for (const fixture of fixtures) {
        let strict = false, draft = false;
        try {
            const grid = app.parseAscii(fixture.ascii);
            strict = app.diagnose(grid).length === 0;
            draft = !app.diagnose(grid).some(error => !error.draft);
        } catch (error) { assert.match(error.message, /unsupported|map|label/i); }
        assert.equal(strict, fixture.valid, fixture.name);
        assert.equal(draft, fixture.valid || fixture.draft, fixture.name);
    }
});

test("Python accepts the same finished maps and draws matching SVG geometry/symbols", () => {
    const inputs = fixtures.map(fixture => ({ ascii: fixture.ascii }));
    for (const fixture of fixtures.filter(fixture => fixture.valid)) {
        for (const playerView of [false, true]) {
            for (const cornerRadius of [0, 0.35, 0.5]) {
                const options = { roughness: 0, cornerRadius, playerView, feetPerSquare: 5 };
                inputs.push({ ascii: fixture.ascii, options, svg: app.renderSvg(app.parseAscii(fixture.ascii), options) });
            }
        }
    }
    for (const size of [2, 3, 4]) {
        for (const tile of "SsZ") {
            for (const corner of ["NW", "NE", "SW", "SE"]) {
                for (const center of [" ", "#"]) {
                    const rows = Array.from({ length: 8 }, () => Array(8).fill("#"));
                    const run = app.spiralAt(2, 2, size, tile, corner);
                    for (const [x, y] of run.cells) rows[y][x] = tile;
                    for (const [x, y] of run.landing) rows[y][x] = " ";
                    if (size === 3) rows[3][3] = center;
                    const grid = new app.Grid(rows.map(row => row.join("")));
                    inputs.push({ ascii: grid.toAscii(), svg: app.renderSvg(grid) });
                }
            }
        }
    }
    const reference = spawnSync(process.env.PYTHON || "python", [path.join(__dirname, "python_reference.py")], {
        input: JSON.stringify(inputs), encoding: "utf8", maxBuffer: 32 * 1024 * 1024,
        env: { ...process.env, PYTHONUTF8: "1" }
    });
    assert.equal(reference.status, 0, reference.stderr || String(reference.error));
    const results = JSON.parse(reference.stdout);
    for (let i = 0; i < fixtures.length; i++) assert.equal(results[i].valid, fixtures[i].valid, fixtures[i].name);
    results.forEach((result, i) => {
        if (!result.valid) return;
        assert.equal(result.tiles, [...app.TILES].sort().join(""));
        assert.equal(result.ascii, app.parseAscii(inputs[i].ascii).toAscii());
        if (result.expected) assert.deepEqual(result.actual, result.expected, `SVG parity for ${inputs[i].ascii}`);
    });
});

test("b halves and spirals can be entered individually and errors resolve", () => {
    const document = new app.Document(app.Grid.stone(8, 8));
    const paint = (x, y, tile) => { document.beginStroke(); document.paint([[x, y]], tile); document.endStroke(); };
    paint(1, 1, "b");
    assert.equal(document.errors[0].code, "incomplete-door");
    assert.throws(() => app.renderSvg(document.grid), /adjacent b/);
    paint(2, 1, "b");
    assert.equal(document.errors.length, 0);
    assert.equal((app.renderSvg(document.grid).match(/data-tile="b"/g) || []).length, 1);
    document.beginStroke();
    assert.throws(() => document.paint([[3, 1]], "b"), /isolated/);
    document.endStroke();
    assert.equal(document.grid.tile(3, 1), "#");
    const run = app.spiralAt(3, 3, 3, "s", "NW");
    paint(3, 3, " ");
    for (const [x, y] of run.cells) paint(x, y, "s");
    assert.equal(document.errors.length, 0);
    document.undo();
    assert.ok(document.errors.some(error => error.code === "incomplete-spiral"));
    document.redo();
    assert.equal(document.errors.length, 0);
});

test("ordinary invalid edits are atomic, including when another structure is incomplete", () => {
    const document = new app.Document(app.Grid.stone(10, 10));
    document.beginStroke();
    document.paint([[1, 1]], "b");
    const before = document.grid.toAscii();
    for (const tile of ["d", "x", "c", "/", "|"]) {
        assert.throws(() => document.paint([[5, 5]], tile));
        assert.equal(document.grid.toAscii(), before);
    }
    document.endStroke();
    assert.equal(document.undoStack.length, 1);
    document.undo();
    assert.equal(document.grid.tile(1, 1), "#");
    document.redo();
    assert.equal(document.grid.tile(1, 1), "b");
});

test("square brushes clip at edges, interpolate fast strokes, and undo as one transaction", () => {
    const document = new app.Document(app.Grid.stone(10, 10));
    document.beginStroke();
    document.paint([[0, 0]], " ", 3);
    document.paint(app.lineCells([1, 1], [8, 7]), " ");
    document.endStroke();
    assert.equal(document.grid.tile(0, 0), " ");
    assert.equal(document.grid.tile(2, 0), "#");
    for (const [x, y] of app.lineCells([1, 1], [8, 7])) assert.equal(document.grid.tile(x, y), " ");
    assert.equal(document.undoStack.length, 1);
    document.undo();
    assert.equal(document.grid.toAscii(), app.Grid.stone(10, 10).toAscii());
    document.redo();
    document.beginStroke();
    document.paint([[9, 9]], ".");
    document.endStroke();
    assert.equal(document.canRedo, false);
});

test("2x2 strokes cover whole squares, clip at edges, and undo together", () => {
    const document = new app.Document(app.Grid.stone(6, 6));
    const original = document.grid.toAscii();
    document.beginStroke();
    document.paint(app.lineCells([1, 1], [3, 1]), " ", 2);
    document.endStroke();
    assert.equal(document.grid.toAscii(), "######\n#    #\n#    #\n######\n######\n######\n");
    document.undo();
    assert.equal(document.grid.toAscii(), original);
    document.redo();
    assert.equal(document.grid.tile(4, 2), " ");
    document.beginStroke();
    document.paint([[5, 5]], ".", 2);
    document.endStroke();
    assert.equal(document.grid.rows[5], "#####.");
    assert.equal(document.grid.tile(4, 5), "#");
    document.undo();
    assert.equal(document.grid.tile(5, 5), "#");
    document.beginStroke();
    assert.throws(() => document.paint([[1, 1]], " ", 7), /Brush size/);
    document.endStroke();
});

test("resize preserves the top-left, detects cropping, and restores dimensions on undo", () => {
    const document = new app.Document(app.parseAscii("####\n# C#\n####\n"));
    const original = document.grid.toAscii();
    document.resize(6, 5);
    assert.equal(document.grid.tile(2, 1), "C");
    assert.equal(document.grid.tile(5, 4), "#");
    assert.ok(app.cropsContent(document.grid, 2, 2));
    document.resize(2, 2);
    document.undo();
    assert.equal(document.grid.width, 6);
    assert.equal(document.grid.tile(2, 1), "C");
    document.undo();
    assert.equal(document.grid.toAscii(), original);
    assert.throws(() => document.resize(10000, 10000), /dimensions/);
});

test("move shifts every tile, fills with stone, blocks loss, and supports undo", () => {
    const document = new app.Document(app.parseAscii("########\n# bb C##\n########\n########\n"));
    const original = document.grid.toAscii();
    for (const [dx, dy] of [[1, 1], [-1, 0], [0, -1], [0, 1]]) {
        document.move(dx, dy);
        assert.equal(document.grid.tile(2 + dx, 1 + dy), "b");
        assert.equal(document.grid.tile(5 + dx, 1 + dy), "C");
        document.undo();
        assert.equal(document.grid.toAscii(), original);
    }
    assert.throws(() => document.move(3, 0), /Expand the map first/);
    assert.throws(() => document.move(0, -2), /Expand the map first/);
    assert.equal(document.grid.toAscii(), original);
    const length = document.undoStack.length;
    document.move(0, 0);
    assert.equal(document.undoStack.length, length);
});

test("loading drafts retains scale and does not replace the document on invalid input", () => {
    const document = new app.Document();
    document.setScale(5);
    const draft = app.parseAscii("####\n#b##\n####\n");
    document.load(draft);
    assert.equal(document.feetPerSquare, 5);
    assert.equal(document.dirty, false);
    assert.throws(() => document.load(app.parseAscii("#d#\n")));
    assert.equal(document.grid, draft);
    assert.equal(document.grid.toAscii(), "####\n#b##\n####\n");
});

test("scale changes SVG dimensions without changing terrain and validates finite inputs", () => {
    const document = new app.Document(app.parseAscii("  \n"));
    const ascii = document.grid.toAscii();
    document.setScale(5);
    assert.match(app.renderSvg(document.grid, { feetPerSquare: document.feetPerSquare }), /width="0.21in"/);
    assert.equal(document.grid.toAscii(), ascii);
    for (const value of [0, -1, NaN, Infinity, "5"]) assert.throws(() => document.setScale(value), /finite/);
    assert.throws(() => app.renderSvg(document.grid, { feetPerSquare: 0 }));
});

test("rough rendering is reproducible, bounded, and independent of Python RNG", () => {
    const grid = app.parseAscii("########\n#......#\n#......#\n########\n");
    const first = app.renderSvg(grid, { seed: 7, cornerRadius: 0.5 });
    assert.equal(app.renderSvg(grid, { seed: 7, cornerRadius: 0.5 }), first);
    assert.notEqual(app.renderSvg(grid, { seed: 8, cornerRadius: 0.5 }), first);
    for (const match of first.matchAll(/x[12]="([^"]+)" y[12]="([^"]+)"/g)) {
        assert.ok(Number(match[1]) >= 0 && Number(match[1]) <= grid.width);
        assert.ok(Number(match[2]) >= 0 && Number(match[2]) <= grid.height);
    }
    for (const options of [{ roughness: 0.3 }, { roughSegments: 1 }, { cornerRadius: 0.6 }, { seed: NaN }]) {
        assert.throws(() => app.renderSvg(grid, options));
    }
});

test("metadata is escaped and editor limits are checked before allocation", () => {
    const svg = app.renderSvg(app.parseAscii(" "), { encounterLabels: [[[0, 0], '<script>&"']] });
    assert.match(svg, /&lt;script&gt;&amp;&quot;/);
    assert.doesNotMatch(svg, /<script>/);
    assert.throws(() => app.Grid.stone(256, 256), /at most/);
    assert.throws(() => app.parseAscii("x".repeat(app.LIMITS.fileBytes + 1)), /smaller/);
    assert.throws(() => app.parseAscii("\n".repeat(1000)), /dimensions/);
});

test("labels roundtrip, edit atomically, survive painting, and follow undo, resize, and moves", () => {
    const original = "#####\n# T##\n#####\n#####\n\n0,0: Stone: <&>\n2,1: 12\n";
    const document = new app.Document(app.parseAscii(original));
    assert.equal(document.grid.toAscii(), original);
    document.setLabel(0, 0, "Updated");
    assert.equal(document.dirty, true);
    document.undo();
    assert.equal(document.grid.toAscii(), original);
    assert.equal(document.dirty, false);
    document.redo();
    document.beginStroke();
    document.paint([[0, 0]], " ");
    document.endStroke();
    document.undo();
    assert.equal(document.grid.tile(0, 0), "#");
    assert.equal(document.grid.labels[0][1], "Updated");
    document.redo();
    assert.equal(document.grid.labels[0][1], "Updated");
    const beforeMove = document.grid.toAscii();
    assert.throws(() => document.move(-1, 0), /Expand the map first/);
    assert.equal(document.grid.toAscii(), beforeMove);
    document.move(1, 1);
    assert.deepEqual(document.grid.labels, [[[1, 1], "Updated"], [[3, 2], "12"]]);
    document.undo();
    assert.equal(document.grid.toAscii(), beforeMove);
    assert.ok(app.cropsContent(document.grid, 2, 2));
    document.resize(2, 2);
    assert.deepEqual(document.grid.labels, [[[0, 0], "Updated"]]);
    document.undo();
    assert.equal(document.grid.toAscii(), beforeMove);
    document.setLabel(0, 0, "");
    assert.deepEqual(document.grid.labels, [[[2, 1], "12"]]);
    document.undo();
    assert.equal(document.grid.toAscii(), beforeMove);
    for (const [x, y, text] of [[5, 0, "outside"], [0.5, 0, "fraction"], [0, 0, "a\nb"]]) {
        assert.throws(() => document.setLabel(x, y, text));
        assert.equal(document.grid.toAscii(), beforeMove);
    }
    assert.match(app.renderSvg(document.grid), /Updated/);
    assert.doesNotMatch(app.renderSvg(document.grid, { showLabels: false }), /id="encounters"/);
    const stoneLabel = new app.Document(app.parseAscii("###\n\n0,0: Stone\n2,0: Cropped\n"));
    assert.ok(app.cropsContent(stoneLabel.grid, 2, 1));
    assert.throws(() => stoneLabel.move(-1, 0), /discard map labels/);
});
