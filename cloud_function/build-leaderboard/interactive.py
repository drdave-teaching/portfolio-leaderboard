# interactive.py: the race chart and the backtests chart as clickable charts on the public page.
# Each chart gets a row of chips (one per fund, click to turn its line on or off), quick buttons (top 5, bottom 5,
# all, none), and a hover readout. Plain JavaScript and SVG, no libraries. Nicknames are drawn with textContent only.
# The PNG versions are still made and stay linked underneath, for anyone without JavaScript.

import json
import math

import pandas as pd

START_ON = 5          # how many funds are switched on when the page opens (the top of the table)

CSS = """
.ichart { background:white; border:1px solid var(--line); border-radius:10px; padding:12px 12px 8px; }
.ichart .bar { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }
.ichart .bar .lab { color:var(--muted); font-size:12.5px; margin-right:4px; }
.ichart button { font-family:inherit; font-size:12.5px; cursor:pointer; border-radius:999px; }
.ichart .quick { border:1px solid var(--navy); background:white; color:var(--navy); padding:4px 12px; }
.ichart .quick:hover { background:#eef2f7; }
.ichart .chip { border:1px solid var(--line); background:white; color:var(--ink); padding:4px 10px 4px 8px; }
.ichart .chip .dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; vertical-align:-1px; }
.ichart .chip.off { color:#9aa6b5; }
.ichart .chip.off .dot { background:#d5dbe3 !important; }
.ichart .chips { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:6px; }
.ichart .find { border:1px solid var(--line); border-radius:999px; padding:4px 12px; font-family:inherit; font-size:12.5px; min-width:150px; }
.ichart .plot { position:relative; }
.ichart svg { display:block; width:100%; }
.ichart .tip { position:absolute; pointer-events:none; background:rgba(19,35,58,0.94); color:white; font-size:12px;
               border-radius:8px; padding:8px 10px; line-height:1.45; display:none; white-space:nowrap; z-index:5; }
.ichart .tip .d { font-weight:700; margin-bottom:2px; }
.ichart .count { color:var(--muted); font-size:12.5px; margin-left:auto; }
details.png { margin-top:6px; } details.png summary { color:var(--muted); font-size:12.5px; cursor:pointer; }
"""

JS = r"""
function lbChart(id, data, startOn) {
  var COLORS = ['#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd','#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf',
                '#0b4f8a','#b35c00','#1b6e1b','#8f1d1d','#5e3c99','#5c3a2e','#a8327a','#4d4d4d','#7d7d14','#0e7f8c'];
  var NS = 'http://www.w3.org/2000/svg';
  var box = document.getElementById(id);
  var n = data.series.length;
  var on = [];
  for (var i = 0; i < n; i++) { on.push(i < startOn); }
  var hover = -1;

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) { e.className = cls; } if (text !== undefined) { e.textContent = text; } return e; }
  function sv(tag, attrs) { var e = document.createElementNS(NS, tag); for (var k in attrs) { e.setAttribute(k, attrs[k]); } return e; }
  function color(i) { return COLORS[i % COLORS.length]; }
  function dash(i) { return i < COLORS.length ? '' : '6 4'; }
  function count(vals) { var k = 0; for (var j = 0; j < vals.length; j++) { if (vals[j] !== null) { k++; } } return k; }
  function valueAt(vals, j) { var first = -1, last = -1; for (var k = 0; k < vals.length; k++) { if (vals[k] !== null) { if (first < 0) { first = k; } last = k; } } if (first < 0 || j < first || j > last) { return null; } while (vals[j] === null) { j--; } return vals[j]; }
  function money(v) { return '$' + Math.round(v).toLocaleString('en-US'); }
  function shortDate(s) { var d = new Date(s + 'T12:00:00'); return d.toLocaleDateString('en-US', {month:'short', day:'numeric'}); }

  var bar = el('div', 'bar');
  bar.appendChild(el('span', 'lab', 'Show:'));
  var quick = [['Top 5', function () { setOn(function (i) { return i < 5; }); }],
               ['Bottom 5', function () { setOn(function (i) { return i >= n - 5; }); }],
               ['All', function () { setOn(function () { return true; }); }],
               ['None', function () { setOn(function () { return false; }); }]];
  for (var q = 0; q < quick.length; q++) { var b = el('button', 'quick', quick[q][0]); b.onclick = quick[q][1]; bar.appendChild(b); }
  var find = el('input', 'find');
  find.type = 'search';
  find.placeholder = 'Find a fund…';
  find.oninput = function () {
    var t = find.value.trim().toLowerCase();
    if (t === '') { return; }
    setOn(function (i) { return data.series[i].name.toLowerCase().indexOf(t) >= 0; });
  };
  bar.appendChild(find);
  var count = el('span', 'count');
  bar.appendChild(count);
  box.appendChild(bar);

  var chipRow = el('div', 'chips');
  var chips = [];
  for (var c = 0; c < n; c++) {
    (function (i) {
      var chip = el('button', 'chip');
      var dot = el('span', 'dot');
      dot.style.background = color(i);
      chip.appendChild(dot);
      chip.appendChild(document.createTextNode((data.ranked ? (i + 1) + '. ' : '') + data.series[i].name));
      chip.onclick = function () { on[i] = !on[i]; refresh(); };
      chip.onmouseenter = function () { hover = i; draw(); };
      chip.onmouseleave = function () { hover = -1; draw(); };
      chips.push(chip);
      chipRow.appendChild(chip);
    })(c);
  }
  box.appendChild(chipRow);

  var plot = el('div', 'plot');
  var tip = el('div', 'tip');
  plot.appendChild(tip);
  box.appendChild(plot);
  var svg = null;
  var geom = null;

  function setOn(rule) { for (var i = 0; i < n; i++) { on[i] = rule(i); } refresh(); }
  function refresh() {
    var k = 0;
    for (var i = 0; i < n; i++) { chips[i].className = on[i] ? 'chip' : 'chip off'; if (on[i]) { k++; } }
    count.textContent = k + ' of ' + n + ' funds shown';
    draw();
  }

  function draw() {
    if (svg) { plot.removeChild(svg); }
    var W = Math.max(plot.clientWidth, 300);
    var H = W < 600 ? 300 : 400;
    var L = W < 600 ? 58 : 70, R = 14, T = 12, B = 34;
    svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, height: H});
    var m = data.dates.length;
    var lo = Infinity, hi = -Infinity;
    function scan(vals) { for (var j = 0; j < vals.length; j++) { var v = vals[j]; if (v !== null) { if (v < lo) { lo = v; } if (v > hi) { hi = v; } } } }
    for (var i = 0; i < n; i++) { if (on[i]) { scan(data.series[i].values); } }
    if (data.benchmark) { scan(data.benchmark.values); }
    scan([10000]);
    var pad = Math.max((hi - lo) * 0.08, 50);
    lo -= pad; hi += pad;
    var ms = [];
    for (var q2 = 0; q2 < m; q2++) { ms.push(new Date(data.dates[q2] + 'T12:00:00').getTime()); }
    function X(j) {
      if (m < 2) { return L; }
      if (data.timeAxis) { return L + (W - L - R) * (ms[j] - ms[0]) / (ms[m - 1] - ms[0]); }
      return L + (W - L - R) * j / (m - 1);
    }
    function Y(v) { return T + (H - T - B) * (hi - v) / (hi - lo); }
    geom = {X: X, Y: Y, L: L, R: R, W: W, H: H, T: T, B: B, m: m};

    // y grid + labels
    var raw = (hi - lo) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = mag;
    var steps = [1, 2, 2.5, 5, 10];
    for (var s = 0; s < steps.length; s++) { if (steps[s] * mag >= raw) { step = steps[s] * mag; break; } }
    for (var y = Math.ceil(lo / step) * step; y <= hi; y += step) {
      svg.appendChild(sv('line', {x1: L, x2: W - R, y1: Y(y), y2: Y(y), stroke: '#eef1f5'}));
      var t = sv('text', {x: L - 8, y: Y(y) + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#5b6b80'});
      t.textContent = money(y);
      svg.appendChild(t);
    }
    svg.appendChild(sv('line', {x1: L, x2: W - R, y1: Y(10000), y2: Y(10000), stroke: '#b9c2ce', 'stroke-dasharray': '5 4'}));
    // x labels
    var every = Math.max(1, Math.ceil(m / (W < 600 ? 4 : 8)));
    for (var j = 0; j < m; j += every) {
      var tx = sv('text', {x: X(j), y: H - B + 18, 'text-anchor': 'middle', 'font-size': 11, fill: '#5b6b80'});
      tx.textContent = shortDate(data.dates[j]);
      svg.appendChild(tx);
    }
    svg.appendChild(sv('line', {x1: L, x2: W - R, y1: H - B, y2: H - B, stroke: '#cfd6df'}));

    function line(vals, stroke, width, dashes, opacity) {
      var d = '', pen = false;
      for (var j = 0; j < vals.length; j++) {
        if (vals[j] === null) { continue; }
        d += (pen ? 'L' : 'M') + X(j).toFixed(1) + ' ' + Y(vals[j]).toFixed(1);
        pen = true;
      }
      if (d === '') { return; }
      var p = sv('path', {d: d, fill: 'none', stroke: stroke, 'stroke-width': width, 'stroke-linejoin': 'round', opacity: opacity});
      if (dashes) { p.setAttribute('stroke-dasharray', dashes); }
      svg.appendChild(p);
      if (count(vals) <= 40) {
        for (var k = 0; k < vals.length; k++) {
          if (vals[k] !== null) { svg.appendChild(sv('circle', {cx: X(k), cy: Y(vals[k]), r: width > 2.5 ? 3 : 2.4, fill: stroke, opacity: opacity})); }
        }
      }
    }
    for (var i2 = n - 1; i2 >= 0; i2--) {
      if (!on[i2] || i2 === hover) { continue; }
      line(data.series[i2].values, color(i2), 2, dash(i2), hover >= 0 ? 0.25 : 0.9);
    }
    if (data.benchmark) { line(data.benchmark.values, '#111111', 3.2, '', 1); }
    if (hover >= 0) { line(data.series[hover].values, color(hover), 4, '', 1); }
    var guide = sv('line', {x1: 0, x2: 0, y1: T, y2: H - B, stroke: '#13233a', 'stroke-opacity': 0.25, visibility: 'hidden'});
    svg.appendChild(guide);
    svg.onmousemove = function (ev) { readout(ev, guide); };
    svg.onmouseleave = function () { tip.style.display = 'none'; guide.setAttribute('visibility', 'hidden'); };
    plot.appendChild(svg);
  }

  function readout(ev, guide) {
    var r = svg.getBoundingClientRect();
    var px = (ev.clientX - r.left) * geom.W / r.width;
    var j = 0;
    for (var c = 1; c < geom.m; c++) { if (Math.abs(geom.X(c) - px) < Math.abs(geom.X(j) - px)) { j = c; } }
    guide.setAttribute('x1', geom.X(j)); guide.setAttribute('x2', geom.X(j)); guide.setAttribute('visibility', 'visible');
    var rows = [];
    for (var i = 0; i < n; i++) { var v = valueAt(data.series[i].values, j); if (on[i] && v !== null) { rows.push([v, data.series[i].name, color(i)]); } }
    if (data.benchmark) { var bv = valueAt(data.benchmark.values, j); if (bv !== null) { rows.push([bv, data.benchmark.name, '#111111']); } }
    rows.sort(function (a, b) { return b[0] - a[0]; });
    while (tip.firstChild) { tip.removeChild(tip.firstChild); }
    tip.appendChild(el('div', 'd', shortDate(data.dates[j])));
    var shown = Math.min(rows.length, 12);
    for (var k = 0; k < shown; k++) {
      var row = el('div');
      var dot = el('span');
      dot.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:' + rows[k][2];
      row.appendChild(dot);
      row.appendChild(document.createTextNode(rows[k][1] + '  ' + money(rows[k][0])));
      tip.appendChild(row);
    }
    if (rows.length > shown) { tip.appendChild(el('div', '', '… and ' + (rows.length - shown) + ' more')); }
    tip.style.display = 'block';
    var left = (ev.clientX - r.left) + 14;
    if (left + tip.offsetWidth > r.width) { left = (ev.clientX - r.left) - tip.offsetWidth - 14; }
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = '8px';
  }

  refresh();
  var waiting = null;
  window.addEventListener('resize', function () { clearTimeout(waiting); waiting = setTimeout(draw, 150); });
}
"""


def clean(v):
    """A JSON-safe number: rounded, or None for a missing day."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 2)


def on_dates(series_by_date, dates):
    out = []
    for d in dates:
        out.append(clean(series_by_date.get(d)))
    return out


def race_data(values, board, benchmark_path):
    """Every fund's with-rules value by day, in leaderboard order, plus the S&P 500. None until two closes."""
    rules = values[values["portfolio"] == "with_rules"]
    if len(rules) == 0 or rules["date"].nunique() < 2:
        return None
    dates = sorted(rules["date"].unique())
    series = []
    for i in range(len(board)):
        netid = board.loc[i, "netid"]
        mine = rules[rules["netid"] == netid]
        by_date = {}
        for k in range(len(mine)):
            by_date[mine["date"].iloc[k]] = mine["value"].iloc[k]
        series.append({"name": str(board.loc[i, "nickname"]), "values": on_dates(by_date, dates)})
    benchmark = None
    if len(benchmark_path) > 0:
        by_date = {}
        for day in benchmark_path.index:
            by_date[pd.Timestamp(day).strftime("%Y-%m-%d")] = benchmark_path.loc[day]
        benchmark = {"name": "S&P 500 (SPY)", "values": on_dates(by_date, dates)}
    return {"dates": dates, "series": series, "benchmark": benchmark, "ranked": True}


def paths_data(named_paths, spy_path):
    """[(name, {date: value})] in ranking order, plus the S&P 500 path, on one shared list of dates."""
    dates = set()
    for name, path in named_paths:
        for d in path:
            dates.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
    if spy_path is not None:
        for d in spy_path:
            dates.add(pd.Timestamp(d).strftime("%Y-%m-%d"))
    dates = sorted(dates)
    if len(dates) < 2:
        return None
    series = []
    for name, path in named_paths:
        by_date = {}
        for d in path:
            by_date[pd.Timestamp(d).strftime("%Y-%m-%d")] = path[d]
        series.append({"name": str(name), "values": on_dates(by_date, dates)})
    benchmark = None
    if spy_path is not None:
        by_date = {}
        for d in spy_path:
            by_date[pd.Timestamp(d).strftime("%Y-%m-%d")] = spy_path[d]
        benchmark = {"name": "S&P 500 (SPY)", "values": on_dates(by_date, dates)}
    return {"dates": dates, "series": series, "benchmark": benchmark, "ranked": True, "timeAxis": True}


def safe_json(data):
    """JSON that cannot close the <script> tag it sits in."""
    text = json.dumps(data, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def block(chart_id, data, png_src, png_alt):
    """The clickable chart, with the old PNG tucked underneath."""
    out = []
    out.append("<div class='ichart' id='%s'></div>" % chart_id)
    out.append("<script>lbChart('%s', %s, %d);</script>" % (chart_id, safe_json(data), START_ON))
    if png_src is not None:
        out.append("<details class='png'><summary>Picture version (every fund at once)</summary>"
                   "<img class='chart' src='%s' alt='%s'></details>" % (png_src, png_alt))
    out.append("<noscript><img class='chart' src='%s' alt='%s'></noscript>" % (png_src or "", png_alt))
    return "".join(out)
