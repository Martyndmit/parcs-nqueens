#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Моделювання балансування навантаження для стратегій block / cyclic / dynamic.

1. Вимірює час розв'язання кожної задачі (префікса) окремо на поточній машині.
2. Для p = 1..P моделює розподіл задач між p ідеальними воркерами (без накладних
   витрат на мережу) і обчислює час "найдовшого" воркера (makespan),
   прискорення S = sum(cost) / makespan та дисбаланс max/mean.
Час кожної задачі вимірюється --repeats разів, береться мінімум (менше шуму).

  python3 bench/simulate_balance.py --n 15 --depth 2 --max-p 8
Результат: results/simulation_n<N>.csv і results/simulation_n<N>.png
"""
import argparse
import csv
import heapq
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
import nqueens_parallel as nq  # noqa: E402


def simulate(costs, p, strategy):
    if strategy in ('block', 'cyclic'):
        parts = nq.split_tasks(list(range(len(costs))), p, strategy)
        loads = [sum(costs[i] for i in part) for part in parts]
    else:  # dynamic: наступна задача - першому воркеру, що звільнився
        loads = [0.0] * p
        heap = [(0.0, i) for i in range(p)]
        for c in costs:
            t, i = heapq.heappop(heap)
            loads[i] += c
            heapq.heappush(heap, (t + c, i))
    makespan = max(loads)
    return makespan, makespan / (sum(loads) / p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=15)
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--max-p', type=int, default=8)
    ap.add_argument('--repeats', type=int, default=3, help='вимірювань на задачу (береться мінімум)')
    args = ap.parse_args()

    tasks = nq.generate_tasks(args.n, args.depth)
    costs = []
    for task in tasks:
        best = None
        for _ in range(args.repeats):
            t0 = time.time()
            nq.solve_tasks(args.n, [task])
            dt = time.time() - t0
            best = dt if best is None else min(best, dt)
        costs.append(best)
    total = sum(costs)
    print('n=%d depth=%d: %d tasks, total %.2f s, task time min %.3f / mean %.3f / max %.3f s'
          % (args.n, args.depth, len(tasks), total, min(costs), total / len(costs), max(costs)))

    out = os.path.join(ROOT, 'results', 'simulation_n%d' % args.n)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    rows = []
    for p in range(1, args.max_p + 1):
        for strategy in ('block', 'cyclic', 'dynamic'):
            makespan, imbalance = simulate(costs, p, strategy)
            rows.append({'p': p, 'strategy': strategy, 'makespan': round(makespan, 4),
                         'speedup': round(total / makespan, 3), 'imbalance': round(imbalance, 3)})
    with open(out + '.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['p', 'strategy', 'makespan', 'speedup', 'imbalance'])
        w.writeheader()
        w.writerows(rows)
    with open(out + '_tasks.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['task', 'weight', 'prefix', 'seconds'])
        for i, (task, c) in enumerate(zip(tasks, costs)):
            w.writerow([i, task[0], ' '.join(map(str, task[1:])), round(c, 5)])

    print('p  ' + '  '.join('%-18s' % s for s in ('block S/imb', 'cyclic S/imb', 'dynamic S/imb')))
    for p in range(1, args.max_p + 1):
        cells = []
        for s in ('block', 'cyclic', 'dynamic'):
            r = next(r for r in rows if r['p'] == p and r['strategy'] == s)
            cells.append('%5.2f / %5.3f     ' % (r['speedup'], r['imbalance']))
        print('%-2d %s' % (p, ' '.join(cells)))

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib not installed - chart skipped')
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from plot_results import COLORS, IDEAL, LABELS, TEXT, end_labels, style
    ps = list(range(1, args.max_p + 1))
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    ax.plot(ps, ps, color=IDEAL, linewidth=1.2, linestyle='--', label='ідеальне S = p')
    ends = []
    for s in ('dynamic', 'cyclic', 'block'):
        ys = [next(r['speedup'] for r in rows if r['p'] == p and r['strategy'] == s) for p in ps]
        ax.plot(ps, ys, color=COLORS[s], linewidth=2, marker='o', markersize=7,
                markeredgecolor='white', markeredgewidth=1.5, label=LABELS[s])
        ends.append((ps[-1], ys[-1]))
    ax.set_xticks(ps)
    ax.set_xlim(0.6, args.max_p + 0.8)
    ax.set_ylim(bottom=0)
    end_labels(ax, ends, lambda v: '%.2f' % v)
    style(ax, 'Модель: прискорення за стратегіями розподілу, N = %d' % args.n,
          'Кількість воркерів p', 'Прискорення S (без мережевих витрат)')
    ax.legend(frameon=False, fontsize=8, labelcolor=TEXT)
    fig.tight_layout()
    fig.savefig(out + '.png')
    print('Saved %s.csv, %s.png' % (out, out))


if __name__ == '__main__':
    main()
