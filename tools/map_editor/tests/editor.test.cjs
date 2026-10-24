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
                for (const roughness of [0, 0.5]) {
                    const options = { roughness, cornerRadius, playerView, feetPerSquare: 5, seed: 7 };
                    inputs.push({ ascii: fixture.ascii, options, svg: app.renderSvg(app.parseAscii(fixture.ascii), options) });
                }
            }
        }
    }
    for (const tile of app.STRAIGHT) {
        for (const rows of [[tile.repeat(4), tile.repeat(4)], [tile.repeat(3), tile + "##", tile.repeat(3)]]) {
            const grid = new app.Grid(rows), options = { feetPerSquare: 5 };
            inputs.push({ ascii: grid.toAscii(), options, svg: app.renderSvg(grid, options) });
        }
    }
    for (const size of [2, 3, 4, 6]) {
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

test("centered door lines and spirals can be entered individually and errors resolve", () => {
    const document = new app.Document(app.Grid.stone(8, 8));
    const paint = (x, y, tile) => { document.beginStroke(); document.paint([[x, y]], tile); document.endStroke(); };
    paint(1, 1, "b");
    assert.equal(document.errors[0].code, "incomplete-door");
    assert.throws(() => app.renderSvg(document.grid), /adjacent b/);
    paint(2, 1, "b");
    assert.equal(document.errors.length, 0);
    assert.equal((app.renderSvg(document.grid).match(/data-tile="b"/g) || []).length, 1);
    document.beginStroke();
    document.paint([[3, 1]], "b");
    assert.throws(() => document.paint([[2, 2]], "b"), /straight/);
    document.endStroke();
    assert.equal(document.grid.tile(3, 1), "b");
    assert.equal(document.grid.tile(2, 2), "#");
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
    for (const tile of ["/", "l", "m", "n"]) {
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
    assert.throws(() => document.load(app.parseAscii("dd\nd#\n")));
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

test("rough rendering uses reproducible bounded cubic paths rather than grid-edge segments", () => {
    const grid = app.parseAscii("########\n#......#\n#......#\n########\n");
    const first = app.renderSvg(grid, { seed: 7, cornerRadius: 0.5 });
    assert.equal(app.renderSvg(grid, { seed: 7, cornerRadius: 0.5 }), first);
    assert.notEqual(app.renderSvg(grid, { seed: 8, cornerRadius: 0.5 }), first);
    assert.doesNotMatch(first, /<line\b/);
    const paths = [...first.matchAll(/<path d="([^"]+)"[^>]*data-texture="rough"/g)];
    assert.equal(paths.length, 1);
    for (const [, data] of paths) {
        assert.match(data, / C /);
        assert.ok(data.endsWith(" Z"));
        const coordinates = data.match(/-?\d+(?:\.\d*)?(?:e[+-]?\d+)?/g).map(Number);
        coordinates.forEach((value, axis) => assert.ok(value >= 0 && value <= (axis % 2 ? grid.height : grid.width)));
    }
    for (const options of [{ roughness: 0.5001 }, { roughSegments: 1 }, { cornerRadius: 0.6 }, { seed: NaN }]) {
        assert.throws(() => app.renderSvg(grid, options));
    }
});

test("cavern walk offsets stay within half a square with at most 45-degree lateral steps", () => {
    for (const closed of [false, true]) {
        for (const spacing of [0.25, Math.SQRT2 / 4]) {
            const distances = Array.from({ length: 81 }, (_, index) => index * spacing);
            const limits = Array(81).fill(0.5);
            limits[20] = limits[60] = 0.1;
            for (const random of [() => 0, () => 1, () => 0.37]) {
                const offsets = app.boundedWalk(distances, limits, closed, random);
                assert.ok(Math.abs(offsets[0] - offsets.at(-1)) < 1e-12);
                if (!closed) assert.equal(offsets[0], 0);
                offsets.forEach((offset, index) => {
                    assert.ok(Math.abs(offset) <= limits[index] + 1e-12);
                    if (index) assert.ok(Math.abs(offset - offsets[index - 1]) <= spacing + 1e-12);
                });
            }
        }
    }
});

test("cavern walks cross square borders, follow diagonals and adapt samples on corner bisectors", () => {
    for (const diagonal of [false, true]) {
        const vertices = Array.from({ length: 7 }, (_, index) => [diagonal ? 2 + index : 2, 1 + index]);
        const normal = diagonal ? [-1 / Math.SQRT2, 1 / Math.SQRT2] : [-1, 0];
        for (const random of [() => 0, () => 1]) {
            const points = app.wallWalk(vertices, 10, 10, 0.5, 4, 0.5, random);
            assert.equal(points.length, 25);
            assert.deepEqual(points[0], vertices[0]);
            assert.deepEqual(points.at(-1), vertices.at(-1));
            const offset = (points[8][0] - vertices[0][0]) * normal[0] +
                (points[8][1] - vertices[0][1]) * normal[1];
            assert.ok(Math.abs(offset) > 0.4, "square borders must not reset the random walk");
        }
    }
    const corner = [[1, 1], [2, 1], [2, 2]];
    const inside = app.wallWalk(corner, 5, 5, 0.5, 4, 0.5, () => 1);
    const outside = app.wallWalk(corner, 5, 5, 0.5, 4, 0.5, () => 0);
    assert.equal(inside.length, 7);
    assert.equal(outside.length, 9);
    for (const [points, sign] of [[inside, 1], [outside, -1]]) {
        assert.ok(points.some(([x, y]) => Math.abs(x - 2 + y - 1) < 1e-9 && sign * (y - 1) > 0));
    }
    const grid = app.parseAscii("########\n#  ....#\n#  ....#\n########");
    const edges = app.wallEdges(grid), chains = app.roughWallChains(edges);
    assert.equal(chains.reduce((sum, chain) => sum + chain.length - 1, 0), edges.filter(edge => edge.rough).length);
    for (const chain of chains) {
        const points = app.wallWalk(chain, grid.width, grid.height, 0.5, 4, 0.5, () => 0.9);
        assert.deepEqual(points[0], chain[0]);
        assert.deepEqual(points.at(-1), chain.at(-1));
        assert.ok(app.wallCurve(points, false).startsWith(`M ${chain[0].join(" ")}`));
    }
});

test("metadata is escaped and editor limits are checked before allocation", () => {
    const svg = app.renderSvg(app.parseAscii(" "), { encounterLabels: [[[0, 0], '<script>&"']] });
    assert.match(svg, /&lt;script&gt;&amp;&quot;/);
    assert.doesNotMatch(svg, /<script>/);
    assert.throws(() => app.Grid.stone(513, 512), /dimensions/);
    assert.throws(() => app.parseAscii("x".repeat(app.LIMITS.fileBytes + 1)), /smaller/);
    assert.throws(() => app.parseAscii("\n".repeat(1000)), /dimensions/);
});

test("512x512 maps resize, paint the last square, roundtrip and export at full extent", () => {
    const document = new app.Document(app.parseAscii("C\n"));
    document.resize(512, 512);
    assert.equal(document.grid.width, 512);
    assert.equal(document.grid.height, 512);
    assert.equal(document.grid.tile(0, 0), "C");
    document.beginStroke();
    document.paint([[511, 511]], " ");
    document.endStroke();
    const ascii = document.grid.toAscii();
    assert.equal(app.parseAscii(ascii).toAscii(), ascii);
    assert.match(app.renderSvg(document.grid), /viewBox="-0.05 -0.05 512.1 512.1"/);
    document.undo();
    assert.equal(document.grid.tile(511, 511), "#");
    document.undo();
    assert.equal(document.grid.width, 1);
    assert.throws(() => document.resize(512, 513), /dimensions/);
});

test("door lines draw once, span both axes, and hide whole secret/concealed spans", () => {
    for (const tile of "dxc") {
        for (const horizontal of [true, false]) {
            let rows = ["#######", "#     #", `##${tile.repeat(3)}##`, "#     #", "#######"];
            if (!horizontal) rows = [...rows[0]].map((_, x) => rows.map(row => row[x]).join(""));
            const grid = new app.Grid(rows), svg = app.renderSvg(grid);
            assert.equal((svg.match(new RegExp(`data-tile="${tile}"`, "g")) || []).length, 1);
            assert.match(svg, /width="2.7" height="0.24"/);
            assert.equal(svg.includes("rotate(90 .5 .5)"), !horizontal);
            const player = app.renderSvg(grid, { playerView: true });
            assert.equal(player.includes(`data-tile="${tile}"`), tile === "d");
            if (tile !== "d") assert.match(player, horizontal ?
                /x1="2" y1="2.5" x2="5" y2="2.5"/ : /x1="2.5" y1="2" x2="2.5" y2="5"/);
        }
    }
    for (const [ascii, transform] of [["bb", "translate(0.5 0.5)"], ["b\nb", "translate(0.5 0.5) rotate(90)"]]) {
        assert.ok(app.renderSvg(app.parseAscii(ascii)).includes(`transform="${transform}"`));
    }
});

test("doors paint one tile at a time through solid stone and export one three-square doorway", () => {
    for (const tile of "dxc") {
        for (const horizontal of [true, false]) {
            const document = new app.Document(app.Grid.stone(7, 7));
            for (const step of [2, 3, 4]) {
                document.beginStroke();
                document.paint([horizontal ? [step, 3] : [3, step]], tile);
                document.endStroke();
                assert.equal(document.errors.length, 0);
            }
            const svg = app.renderSvg(document.grid);
            assert.equal((svg.match(new RegExp(`data-tile="${tile}"`, "g")) || []).length, 1);
            assert.match(svg, /width="2.7" height="0.24"/);
            assert.match(svg, /x1="2.85" y1="0.5" x2="3" y2="0.5"/);
            assert.equal(svg.includes("rotate(90 .5 .5)"), !horizontal);
            assert.equal(app.parseAscii(document.grid.toAscii()).toAscii(), document.grid.toAscii());
            document.beginStroke();
            const before = document.grid.toAscii();
            assert.throws(() => document.paint([horizontal ? [3, 4] : [4, 3]], tile), /straight/);
            assert.equal(document.grid.toAscii(), before);
            document.endStroke();
            document.undo();
            assert.equal(document.grid.tile(...(horizontal ? [4, 3] : [3, 4])), "#");
            document.redo();
            assert.equal(document.grid.tile(...(horizontal ? [4, 3] : [3, 4])), tile);
        }
        const svg = app.renderSvg(app.parseAscii(`##${tile.repeat(3)}##`));
        assert.equal((svg.match(new RegExp(`data-tile="${tile}"`, "g")) || []).length, 1);
        assert.match(svg, /width="2.7" height="0.24"/);
    }
});

test("centered doors connect to adjacent terrain with half-square walls at both ends", () => {
    for (const length of [2, 3, 4]) {
        for (const terrain of ["#", " ", ".", "|", "~"]) {
            for (const horizontal of [true, false]) {
                const row = terrain + "b".repeat(length) + terrain;
                const grid = new app.Grid(horizontal ? [row] : [...row]);
                for (const playerView of [false, true]) {
                    const svg = app.renderSvg(grid, { playerView });
                    const lines = [...svg.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"[^>]*data-texture="([^"]+)"/g)];
                    const connectors = lines.slice(-2).map(match => match.slice(1, 5).map(Number));
                    assert.deepEqual(connectors, horizontal ?
                        [[0, 0.5, 0.5, 0.5], [length - 0.5, 0.5, length, 0.5]] :
                        [[0.5, 0, 0.5, 0.5], [0.5, length - 0.5, 0.5, length]]);
                    assert.deepEqual(lines.slice(-2).map(match => match[5]), ["smooth", "smooth"]);
                    assert.equal((svg.match(/data-tile="b"/g) || []).length, 1);
                }
            }
        }
    }
});

test("directional stairs/ramps group full width and length with physical elevation", () => {
    for (const tile of app.STRAIGHT) {
        const grid = new app.Grid([tile.repeat(4), tile.repeat(4)]);
        const svg = app.renderSvg(grid, { feetPerSquare: 5 });
        const horizontal = "FfHhPpRr".includes(tile), length = horizontal ? 4 : 2, width = horizontal ? 2 : 4;
        assert.equal((svg.match(/data-tile=/g) || []).length, 1);
        assert.match(svg, new RegExp(`data-length="${length}" data-width="${width}"`));
        assert.ok(svg.includes(`data-elevation="${length * 5 * (tile === tile.toUpperCase() ? 1 : -1)}"`));
        const facing = "EeOo".includes(tile) ? "north" : "FfPp".includes(tile) ? "east" :
            "GgQq".includes(tile) ? "south" : "west";
        assert.ok(svg.includes(`data-facing="${facing}"`));
        const treads = [...svg.slice(svg.indexOf('<g id="features"')).matchAll(/data-texture=/g)].length;
        assert.equal(treads, "EeFfGgHh".includes(tile) ? 5 * length + 3 : 5);
        const texts = [...svg.matchAll(/<text\b[^>]*>([^<]*)<\/text>/g)].map(match => match[1]);
        assert.deepEqual(texts, "EeFfGgHh".includes(tile) ? [] :
            [`ramp ${tile === tile.toUpperCase() ? "up" : "down"}`]);
        assert.equal((svg.match(/<rect /g) || []).length, 8, "clip preserves the eight painted squares");
    }
    const irregular = app.renderSvg(app.parseAscii("FFF\nF##\nFFF"));
    assert.equal((irregular.match(/<rect /g) || []).length, 7);
    assert.equal((irregular.match(/data-tile=/g) || []).length, 1);
    assert.equal((app.renderSvg(app.parseAscii("F#F")).match(/data-tile=/g) || []).length, 2);
});

test("partitions accept any neighbors, stay smooth in caverns, and block enclosed rooms", () => {
    const grid = app.parseAscii("#####\n#.|.#\n#_L.#\n#####");
    assert.equal(app.diagnose(grid).length, 0);
    const edges = app.wallEdges(grid);
    for (const edge of edges.filter(edge => edge.start[0] === 2 && edge.start[1] <= 1 ||
        edge.start[0] === 1 && edge.start[1] === 3)) assert.equal(edge.rough, false);
    const document = new app.Document(app.Grid.stone(3, 3));
    document.beginStroke();
    document.paint([[0, 0]], "L");
    document.paint([[1, 0]], "|");
    document.paint([[0, 1]], "_");
    document.endStroke();
    assert.equal(document.errors.length, 0);
    document.undo();
    assert.equal(document.grid.tile(0, 0), "#");
});

test("down stairs taper progressively to half width along the arrow while up stairs stay uniform", () => {
    for (const tile of "EeFfGgHh") {
        for (const length of [1, 3, 19]) {
            for (const width of [1, 3]) {
                const horizontal = "FfHh".includes(tile);
                const grid = new app.Grid(Array(horizontal ? width : length).fill(
                    tile.repeat(horizontal ? length : width)));
                const svg = app.renderSvg(grid);
                const feature = svg.slice(svg.indexOf('<g id="features"'));
                const lines = [...feature.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"/g)]
                    .map(match => match.slice(1).map(Number));
                const count = 5 * length, descending = tile === tile.toLowerCase();
                const treads = lines.slice(0, count).reverse();
                assert.equal(lines.length, count + 3);
                const fullWidth = width - 0.3, widths = treads.map(([x1, , x2]) => x2 - x1);
                widths.forEach((actual, index) => {
                    const expected = fullWidth * (descending ? 1 - index / (2 * (count - 1)) : 1);
                    assert.ok(Math.abs(actual - expected) < 1e-9, `${tile}, ${length}x${width}, tread ${index}`);
                    if (descending && index) assert.ok(actual < widths[index - 1]);
                    assert.ok(Math.abs(treads[index][0] + treads[index][2] - width) < 1e-9);
                });

                assert.ok(Math.abs(widths.at(-1) / widths[0] - (descending ? 0.5 : 1)) < 1e-9);
                const arrow = [width / 2, length - 0.18, width / 2, 0.18];
                lines[count].forEach((value, index) => assert.ok(Math.abs(value - arrow[index]) < 1e-9));
            }
        }
    }
});

test("spiral arrows use three-quarter radius and descending treads narrow clockwise from every landing", () => {
    for (const size of [2, 3, 4]) {
        for (const tile of "SsZ") {
            for (const corner of ["NW", "NE", "SW", "SE"]) {
                const rows = Array.from({ length: 8 }, () => Array(8).fill("#"));
                const run = app.spiralAt(2, 2, size, tile, corner);
                for (const [x, y] of run.cells) rows[y][x] = tile;
                for (const [x, y] of run.landing) rows[y][x] = " ";
                const svg = app.renderSvg(new app.Grid(rows.map(row => row.join(""))));
                const feature = svg.slice(svg.indexOf('<g id="features"'));
                const arrows = [...feature.matchAll(/<path d="([^"]+)"[^>]*data-direction="(up|down)"/g)];
                assert.deepEqual(arrows.map(match => match[2]), tile === "Z" ? ["up", "down"] : [tile === "s" ? "down" : "up"]);
                const radius = size / 2, fullWidth = radius - (size === 3 ? 0.5 : 0.12);
                for (const [, path, direction] of arrows) {
                    const coordinates = path.match(/-?\d+(?:\.\d*)?(?:e[+-]?\d+)?/g).map(Number);
                    assert.equal(coordinates[2], radius * 0.75);
                    assert.equal(coordinates[3], radius * 0.75);
                    assert.equal(coordinates[6], direction === "down" ? 1 : 0);
                }
                const treads = [...feature.matchAll(/<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"/g)]
                    .slice(0, -2 * arrows.length).map(match => match.slice(1).map(Number));
                let previous;
                treads.forEach(([x1, y1, x2, y2], index) => {
                    const width = Math.hypot(x2 - x1, y2 - y1);
                    const factor = tile === "s" ? 1 - index / (2 * (treads.length - 1)) : 1;
                    assert.ok(Math.abs(width - fullWidth * factor) < 1e-9);
                    if (tile === "s" && previous) {
                        assert.ok(width < previous.width);
                        assert.ok(previous.dx * (y2 - y1) - previous.dy * (x2 - x1) > 0);
                    }
                    previous = {width, dx: x2 - x1, dy: y2 - y1};
                });
                if (tile === "s") {
                    assert.ok(Math.abs(previous.width - fullWidth / 2) < 1e-9);
                    const landing = [0, 1].map(axis => run.landing.reduce((sum, cell) => sum + cell[axis] + 0.5, 0) / run.landing.length);
                    const firstAngle = Math.atan2(landing[1] - 2 - radius, landing[0] - 2 - radius) + Math.PI / 4;
                    for (const [line, angle] of [[treads[0], firstAngle], [treads.at(-1), firstAngle + 3 * Math.PI / 2]]) {
                        const dx = line[2] - line[0], dy = line[3] - line[1], width = Math.hypot(dx, dy);
                        assert.ok(Math.abs(dx / width - Math.cos(angle)) < 1e-9);
                        assert.ok(Math.abs(dy / width - Math.sin(angle)) < 1e-9);
                    }
                }
            }
        }
    }
});

test("ramps label the center arrow with readable up/down text that fits short and long runs", () => {
    for (const tile of "OoPpQqRr") {
        for (const length of [1, 4]) {
            for (const width of [1, 3]) {
                const horizontal = "PpRr".includes(tile);
                const grid = new app.Grid(Array(horizontal ? width : length).fill(
                    tile.repeat(horizontal ? length : width)));
                for (const playerView of [false, true]) {
                    const svg = app.renderSvg(grid, { playerView }), text = `ramp ${tile === tile.toUpperCase() ? "up" : "down"}`;
                    const annotation = svg.match(/<g transform="translate\(([^)]+)\) rotate\((-?90)\)"><text[^>]*font-size="([^"]+)"[^>]*>(ramp (?:up|down))<\/text><\/g>/);
                    assert.ok(annotation);
                    assert.equal(annotation[4], text);
                    assert.equal((svg.match(/>ramp (?:up|down)<\/text>/g) || []).length, 1);
                    assert.ok(!svg.includes(`>${tile}</text>`));
                    const [x, y] = annotation[1].split(" ").map(Number), size = Number(annotation[3]);
                    assert.ok(size > 0 && size <= 0.22);
                    assert.ok(size * text.length * 0.6 <= length - 0.4 + 1e-9);
                    assert.ok(x > width / 2 && x < width - 0.15);
                    assert.equal(y, length / 2);
                    assert.equal(Number(annotation[2]), "QqRr".includes(tile) ? 90 : -90);
                    const feature = svg.slice(svg.indexOf('<g id="features"'));
                    assert.equal((feature.match(/<line /g) || []).length, 5);
                }
            }
        }
    }
    assert.doesNotMatch(app.renderSvg(app.parseAscii("Ff")), />ramp (?:up|down)</);
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
