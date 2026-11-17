#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Побудова таблиці й графіків за CSV, який записав bench/bench.py.

  python3 bench/plot_results.py results/gcp_n15.csv --label "GCP, n1-standard-1"

Створює поруч із CSV:
  <name>_summary.md      - таблиця: медіанний час, прискорення S = T1/Tp, ефективність E = S/p
  <name>_time.png        - час виконання від кількості воркерів
  <name>_speedup.png     - прискорення (відносно послідовної версії) та ідеальне S = p
  <name>_efficiency.png  - ефективність
Потрібно: pip install matplotlib
"""
import argparse
import csv
import os
import statistics
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

# категоріальні кольори (фіксований порядок), текст і сітка - нейтральні
COLORS = {'dynamic': '#2a78d6', 'cyclic': '#eb6834', 'block': '#1baf7a'}
TEXT = '#0b0b0b'
MUTED = '#52514e'
GRID = '#e4e3df'
IDEAL = '#8a8984'
LABELS = {'dynamic': 'dynamic (мішок задач)', 'cyclic': 'cyclic (по колу)',
          'block': 'block (блоками)'}


def style(ax, title, xlabel, ylabel):
    ax.set_title(title, color=TEXT, fontsize=11, loc='left', pad=10)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ('top', 'right'):
        ax.spines[side].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8)


def end_labels(ax, items, fmt):
    """Підписи значень у кінці ліній; близькі підписи розводяться по вертикалі."""
    if not items:
        return
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.06
    placed = []
    for x, y in sorted(items, key=lambda it: it[1]):
        ty = y if not placed or y - placed[-1][1] >= gap else placed[-1][1] + gap
        placed.append((x, ty, y))
    dx = 0.15
    for x, ty, y in placed:
        ax.text(x + dx, ty, fmt(y), color=TEXT, fontsize=8, va='center', ha='left')


def load(paths):
    rows = []
    for path in paths:
        with open(path, newline='') as f:
            rows.extend(csv.DictReader(f))
    return rows


def summarize(rows, n):
    seq = [float(r['time_total']) for r in rows
           if r['kind'] == 'sequential' and int(r['n']) == n]
    par = defaultdict(list)
    imb = defaultdict(list)
    for r in rows:
        if r['kind'] == 'parallel' and int(r['n']) == n:
            key = (r['strategy'], int(r['workers']))
            par[key].append(float(r['time_total']))
            if r['imbalance']:
                imb[key].append(float(r['imbalance']))
    t_seq = statistics.median(seq) if seq else None
    table = {}
    for (strategy, p), times in par.items():
        t = statistics.median(times)
        base = t_seq if t_seq else statistics.median(par.get((strategy, 1), times))
        s = base / t
        table[(strategy, p)] = {
            'runs': len(times), 'time': t, 'min': min(times), 'max': max(times),
            'speedup': s, 'efficiency': s / p,
            'imbalance': statistics.median(imb[(strategy, p)]) if imb[(strategy, p)] else None,
        }
    return t_seq, len(seq), table


def write_markdown(path, label, n, t_seq, seq_runs, table):
    lines = ['# Результати: %s, N = %d' % (label, n), '']
    if t_seq:
        lines.append('Послідовна версія: T_seq = %.3f с (медіана з %d запусків)' % (t_seq, seq_runs))
        lines.append('')
    lines.append('| Стратегія | p | Запусків | T_p, с (медіана) | min–max, с | S = T_seq/T_p | E = S/p | Дисбаланс |')
    lines.append('|---|---|---|---|---|---|---|---|')
    for (strategy, p) in sorted(table, key=lambda k: (k[0] != 'dynamic', k[0], k[1])):
        r = table[(strategy, p)]
        lines.append('| %s | %d | %d | %.3f | %.3f–%.3f | %.2f | %.2f | %s |' % (
            strategy, p, r['runs'], r['time'], r['min'], r['max'], r['speedup'],
            r['efficiency'], '%.3f' % r['imbalance'] if r['imbalance'] else '–'))
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def series(table, strategy):
    ps = sorted(p for (s, p) in table if s == strategy)
    return ps, [table[(strategy, p)] for p in ps]


def plot(table, t_seq, n, label, prefix):
    strategies = [s for s in ('dynamic', 'cyclic', 'block') if any(k[0] == s for k in table)]
    all_p = sorted(set(p for (_, p) in table))

    def lines(ax, metric):
        ends = []
        for s in strategies:
            ps, rs = series(table, s)
            ys = [r[metric] for r in rs]
            ax.plot(ps, ys, color=COLORS[s], linewidth=2, marker='o', markersize=7,
                    markeredgecolor='white', markeredgewidth=1.5, label=LABELS[s],
                    linestyle='-' if len(ps) > 1 else 'none')
            ends.append((ps[-1], ys[-1]))
        ax.set_xticks(all_p)
        ax.set_xlim(min(all_p) - 0.4, max(all_p) + 0.7)
        return ends

    def label_ends(ax, ends, metric):
        end_labels(ax, ends, (lambda v: '%.1f с' % v) if metric == 'time' else (lambda v: '%.2f' % v))

    # час
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    ends = lines(ax, 'time')
    if t_seq:
        ax.axhline(t_seq, color=IDEAL, linewidth=1.2, linestyle='--', label='послідовна версія')
    ax.set_ylim(bottom=0)
    label_ends(ax, ends, 'time')
    style(ax, 'Час виконання, N = %d (%s)' % (n, label), 'Кількість воркерів p', 'Час, с')
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT)
    fig.tight_layout()
    fig.savefig(prefix + '_time.png')
    plt.close(fig)

    # прискорення
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    ax.plot(all_p, all_p, color=IDEAL, linewidth=1.2, linestyle='--', label='ідеальне S = p')
    ends = lines(ax, 'speedup')
    ax.set_ylim(bottom=0)
    label_ends(ax, ends, 'speedup')
    style(ax, 'Прискорення S = T_seq / T_p, N = %d (%s)' % (n, label),
          'Кількість воркерів p', 'Прискорення S')
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT)
    fig.tight_layout()
    fig.savefig(prefix + '_speedup.png')
    plt.close(fig)

    # ефективність
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    ax.axhline(1.0, color=IDEAL, linewidth=1.2, linestyle='--', label='ідеальна E = 1')
    ends = lines(ax, 'efficiency')
    ax.set_ylim(0, 1.15)
    label_ends(ax, ends, 'efficiency')
    style(ax, 'Ефективність E = S / p, N = %d (%s)' % (n, label),
          'Кількість воркерів p', 'Ефективність E')
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT, loc='lower left')
    fig.tight_layout()
    fig.savefig(prefix + '_efficiency.png')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('csv', nargs='+')
    ap.add_argument('--n', type=int, default=None, help='N (за замовчуванням - найбільше в CSV)')
    ap.add_argument('--label', default='ПАРКС')
    ap.add_argument('--prefix', default=None)
    args = ap.parse_args()

    rows = load(args.csv)
    n = args.n or max(int(r['n']) for r in rows)
    prefix = args.prefix or os.path.splitext(args.csv[0])[0]
    t_seq, seq_runs, table = summarize(rows, n)
    write_markdown(prefix + '_summary.md', args.label, n, t_seq, seq_runs, table)
    plot(table, t_seq, n, args.label, prefix)
    with open(prefix + '_summary.md') as f:
        print(f.read())
    print('Charts: %s_{time,speedup,efficiency}.png' % prefix)


if __name__ == '__main__':
    main()
