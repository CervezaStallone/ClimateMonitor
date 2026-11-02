/* Zone-editor voor het houtdiagram (temperatuur × RV).
 *
 * Tekent over het Plotly-diagram een vorm met sleepbare hoeken (grote bollen) en op elke zijde een
 * middenbol. Een middenbol slepen voegt daar een hoek toe; dubbelklik op een hoek verwijdert hem
 * (minimaal 3). Werkt met muis en touch (pointer events). Na elke wijziging gaan de punten naar de
 * Dash-store 'zone-edit-points'; de server slaat ze op.
 *
 * Aangestuurd door de clientside callback zones.edit met de inhoud van de store 'zone-edit'
 * ({id, points} of null = editor uit).
 */
(function () {
    'use strict';
    var SVG_NS = 'http://www.w3.org/2000/svg';
    var GRAPH_ID = 'wood-chart';
    var editor = { points: null, svg: null, plot: null, drag: null };

    function plotElement() {
        var graph = document.getElementById(GRAPH_ID);
        return graph ? graph.querySelector('.js-plotly-plot') : null;
    }

    function axes(plot) {
        var layout = plot && plot._fullLayout;
        return layout && layout.xaxis && layout.yaxis ? layout : null;
    }

    function toPixels(layout, point) {
        return [layout._size.l + layout.xaxis.l2p(point[0]), layout._size.t + layout.yaxis.l2p(point[1])];
    }

    function toData(layout, x, y) {
        var temp = layout.xaxis.p2l(x - layout._size.l);
        var rh = layout.yaxis.p2l(y - layout._size.t);
        return [Math.round(temp * 10) / 10, Math.round(Math.min(100, Math.max(0, rh)) * 10) / 10];
    }

    function commit() {
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props('zone-edit-points', { data: editor.points.map(function (p) { return p.slice(); }) });
        }
    }

    function circle(cx, cy, radius, className) {
        var c = document.createElementNS(SVG_NS, 'circle');
        c.setAttribute('cx', cx);
        c.setAttribute('cy', cy);
        c.setAttribute('r', radius);
        c.setAttribute('class', className);
        return c;
    }

    function startDrag(event, index) {
        event.preventDefault();
        event.stopPropagation();
        editor.drag = index;
    }

    function draw() {
        var plot = plotElement();
        var layout = axes(plot);
        if (!editor.points || !layout) {
            return;
        }
        var host = plot.querySelector('.svg-container');
        if (!editor.svg || editor.svg.parentNode !== host) {
            editor.svg = document.createElementNS(SVG_NS, 'svg');
            editor.svg.setAttribute('class', 'zone-editor');
            host.appendChild(editor.svg);
        }
        var svg = editor.svg;
        svg.setAttribute('width', layout.width);
        svg.setAttribute('height', layout.height);
        while (svg.firstChild) {
            svg.removeChild(svg.firstChild);
        }
        var pixels = editor.points.map(function (p) { return toPixels(layout, p); });
        var shape = document.createElementNS(SVG_NS, 'polygon');
        shape.setAttribute('points', pixels.map(function (p) { return p.join(','); }).join(' '));
        shape.setAttribute('class', 'zone-editor-shape');
        svg.appendChild(shape);

        // Middenbollen: slepen voegt een hoek toe tussen hoek i en i + 1
        pixels.forEach(function (p, i) {
            var next = pixels[(i + 1) % pixels.length];
            var mid = circle((p[0] + next[0]) / 2, (p[1] + next[1]) / 2, 6, 'zone-editor-mid');
            mid.addEventListener('pointerdown', function (event) {
                editor.points.splice(i + 1, 0, toData(layout, (p[0] + next[0]) / 2, (p[1] + next[1]) / 2));
                startDrag(event, i + 1);
                draw();
            });
            svg.appendChild(mid);
        });
        // Hoeken: slepen; dubbelklik verwijdert (minimaal 3 hoeken)
        pixels.forEach(function (p, i) {
            var corner = circle(p[0], p[1], 8, 'zone-editor-corner');
            corner.addEventListener('pointerdown', function (event) { startDrag(event, i); });
            corner.addEventListener('dblclick', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (editor.points.length > 3) {
                    editor.points.splice(i, 1);
                    draw();
                    commit();
                }
            });
            svg.appendChild(corner);
        });
    }

    function onMove(event) {
        if (editor.drag === null || !editor.points) {
            return;
        }
        var plot = plotElement();
        var layout = axes(plot);
        if (!layout) {
            return;
        }
        var box = plot.querySelector('.svg-container').getBoundingClientRect();
        editor.points[editor.drag] = toData(layout, event.clientX - box.left, event.clientY - box.top);
        draw();
    }

    function onUp() {
        if (editor.drag !== null) {
            editor.drag = null;
            commit();
        }
    }

    function stop() {
        editor.points = null;
        editor.drag = null;
        if (editor.svg && editor.svg.parentNode) {
            editor.svg.parentNode.removeChild(editor.svg);
        }
        editor.svg = null;
    }

    function watchPlot() {
        // Na elke (her)tekening of zoom van Plotly de bollen opnieuw plaatsen
        var plot = plotElement();
        if (plot && plot !== editor.plot && plot.on) {
            editor.plot = plot;
            plot.on('plotly_afterplot', draw);
        }
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);

    window.dash_clientside = Object.assign({}, window.dash_clientside, {
        zones: {
            edit: function (editing) {
                stop();
                if (editing && editing.points) {
                    editor.points = editing.points.map(function (p) { return [Number(p[0]), Number(p[1])]; });
                    watchPlot();
                    // Het diagram wordt mogelijk net opnieuw opgebouwd: tekenen na de volgende frame
                    window.requestAnimationFrame(function () { watchPlot(); draw(); });
                    commit();
                }
                return window.dash_clientside.no_update;
            }
        }
    });
}());
