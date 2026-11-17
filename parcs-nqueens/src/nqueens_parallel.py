# -*- coding: utf-8 -*-
"""
Паралельний підрахунок кількості розв'язків задачі про N ферзів
у системі ПАРКС (PARCS-Python, https://github.com/Hummer12007/parcs-python).

Схема: master -> workers (map) -> master (reduce).

  1. Master читає вхідний файл і будує "задачі": усі коректні розстановки
     ферзів у перших `depth` рядках (з урахуванням дзеркальної симетрії
     першого рядка).
  2. Задачі розподіляються між воркерами однією з трьох стратегій:
       block   - кожен воркер отримує суцільний блок задач;
       cyclic  - задачі роздаються по колу (round-robin);
       dynamic - "мішок задач": воркер отримує нову порцію задач,
                 щойно закінчив попередню (динамічне балансування).
  3. Кожен воркер (метод mymap) для своїх задач рахує кількість
     доповнень до повного розв'язку перебором з поверненням на бітових масках.
  4. Master (метод myreduce) підсумовує результати й записує звіт у вихідний файл.

Код сумісний з Python 2.7 (образ hummer12007/parcs-node) і Python 3.
Формат вхідного файлу (рядки key=value, '#' - коментар):

    n=14            # розмір дошки
    depth=2         # глибина декомпозиції (кількість зафіксованих рядків)
    strategy=dynamic  # block | cyclic | dynamic
    chunk=1         # розмір порції для dynamic

Допускається й короткий формат: перший рядок - лише число N.
"""
from __future__ import division, print_function

import json
import time

from Pyro4 import expose

# OEIS A000170 - кількість розв'язків задачі про N ферзів (для перевірки)
KNOWN_SOLUTIONS = {
    1: 1, 2: 0, 3: 0, 4: 2, 5: 10, 6: 4, 7: 40, 8: 92, 9: 352, 10: 724,
    11: 2680, 12: 14200, 13: 73712, 14: 365596, 15: 2279184,
    16: 14772512, 17: 95815104, 18: 666090624,
}

STRATEGIES = ('block', 'cyclic', 'dynamic')


# ---------------------------------------------------------------------------
# Обчислювальне ядро (однакове для послідовної та паралельної версій)
# ---------------------------------------------------------------------------
def count_completions(full, cols, ld, rd):
    """Кількість способів розставити ферзів у рядках, що залишились.

    full - маска з n одиниць; cols - зайняті стовпці;
    ld / rd - клітинки поточного рядка, які б'ються по діагоналях.
    """
    if cols == full:
        return 1
    total = 0
    avail = full & ~(cols | ld | rd)
    while avail:
        bit = avail & -avail          # наймолодший вільний стовпець
        avail ^= bit
        total += count_completions(full, cols | bit,
                                   ((ld | bit) << 1) & full,
                                   (rd | bit) >> 1)
    return total


def state_from_prefix(n, prefix):
    """Відновлює бітовий стан після розстановки ферзів у стовпці prefix."""
    full = (1 << n) - 1
    cols = ld = rd = 0
    for c in prefix:
        bit = 1 << c
        cols |= bit
        ld = ((ld | bit) << 1) & full
        rd = (rd | bit) >> 1
    return full, cols, ld, rd


def generate_tasks(n, depth):
    """Усі коректні префікси довжини depth: список [weight, c0, c1, ...].

    Дзеркальна симетрія: для ферзя першого рядка беремо лише ліву половину
    стовпців (вага 2), а для непарного n - ще й середній стовпець (вага 1).
    """
    depth = max(1, min(depth, n))
    full = (1 << n) - 1
    tasks = []

    def extend(prefix, weight, cols, ld, rd):
        if len(prefix) == depth or cols == full:
            tasks.append([weight] + prefix)
            return
        avail = full & ~(cols | ld | rd)
        while avail:
            bit = avail & -avail
            avail ^= bit
            extend(prefix + [bit.bit_length() - 1], weight, cols | bit,
                   ((ld | bit) << 1) & full, (rd | bit) >> 1)

    first = [(c, 2) for c in range(n // 2)]
    if n % 2 == 1:
        first.append((n // 2, 1))
    for c, weight in first:
        bit = 1 << c
        extend([c], weight, bit, (bit << 1) & full, bit >> 1)
    return tasks


def split_tasks(tasks, parts, strategy):
    """Статичний розподіл задач між parts воркерами."""
    if strategy == 'block':
        size, rest = divmod(len(tasks), parts)
        result, start = [], 0
        for i in range(parts):
            end = start + size + (1 if i < rest else 0)
            result.append(tasks[start:end])
            start = end
        return result
    # cyclic (round-robin)
    return [tasks[i::parts] for i in range(parts)]


def solve_tasks(n, tasks):
    """Сума weight * (кількість доповнень) по списку задач."""
    total = 0
    for task in tasks:
        full, cols, ld, rd = state_from_prefix(n, task[1:])
        total += task[0] * count_completions(full, cols, ld, rd)
    return total


def parse_input(text):
    params = {'n': None, 'depth': 2, 'strategy': 'dynamic', 'chunk': 1}
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if '=' in line:
            key, value = [s.strip() for s in line.split('=', 1)]
            key = key.lower()
            if key in ('n', 'depth', 'chunk'):
                params[key] = int(value)
            elif key == 'strategy':
                params[key] = value.lower()
        elif params['n'] is None:
            params['n'] = int(line)
    if params['n'] is None or params['n'] < 1:
        raise ValueError('Input must contain N >= 1')
    if params['strategy'] not in STRATEGIES:
        raise ValueError('strategy must be one of %s' % (STRATEGIES,))
    params['chunk'] = max(1, params['chunk'])
    return params


# ---------------------------------------------------------------------------
# Розв'язувач ПАРКС
# ---------------------------------------------------------------------------
class Solver:
    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name
        self.workers = workers
        print("Inited")

    def solve(self):
        print("Job Started")
        t_start = time.time()
        params = self.read_input()
        n, depth = params['n'], params['depth']
        strategy, chunk = params['strategy'], params['chunk']
        p = len(self.workers)
        print("Workers %d, n=%d, depth=%d, strategy=%s" % (p, n, depth, strategy))

        tasks = generate_tasks(n, depth)
        t_tasks = time.time()

        # map
        if strategy == 'dynamic':
            mapped = self.run_dynamic(n, tasks, chunk)
        else:
            parts = split_tasks(tasks, p, strategy)
            futures = []
            for i in range(p):
                # виклик асинхронний: проксі воркера в ПАРКС працює в async-режимі
                futures.append(self.workers[i].mymap(n, parts[i]))
            mapped = [(i, f.value) for i, f in enumerate(futures)]
        t_map = time.time()

        # reduce
        solutions, busy, done = self.myreduce(mapped, p)
        t_end = time.time()

        expected = KNOWN_SOLUTIONS.get(n)
        mean_busy = sum(busy) / len(busy) if busy else 0.0
        result = {
            'kind': 'parallel', 'n': n, 'depth': depth, 'strategy': strategy,
            'chunk': chunk, 'workers': p, 'tasks': len(tasks),
            'solutions': solutions, 'expected': expected,
            'correct': (expected is None) or (solutions == expected),
            'time_total': round(t_end - t_start, 4),
            'time_tasks': round(t_tasks - t_start, 4),
            'time_map': round(t_map - t_tasks, 4),
            'time_reduce': round(t_end - t_map, 4),
            'worker_busy': [round(b, 4) for b in busy],
            'worker_tasks': done,
            'imbalance': round(max(busy) / mean_busy, 4) if mean_busy > 0 else 1.0,
        }
        self.write_output(result)
        print("Job Finished")

    def run_dynamic(self, n, tasks, chunk):
        """Динамічний розподіл ("мішок задач"): нова порція - першому вільному воркеру."""
        queue = [tasks[i:i + chunk] for i in range(0, len(tasks), chunk)]
        queue.reverse()                      # pop() з кінця = видача по порядку
        pending = {}
        mapped = []
        for i in range(len(self.workers)):
            if queue:
                pending[i] = self.workers[i].mymap(n, queue.pop())
        while pending:
            progressed = False
            for i in list(pending.keys()):
                future = pending[i]
                if future.ready:
                    mapped.append((i, future.value))
                    progressed = True
                    if queue:
                        pending[i] = self.workers[i].mymap(n, queue.pop())
                    else:
                        del pending[i]
            if not progressed:
                # опитування (а не Event.wait з тайм-аутом): у Python 2.7
                # wait(timeout) реалізовано через sleep до 50 мс
                time.sleep(0.001)
        return mapped

    @staticmethod
    @expose
    def mymap(n, tasks):
        """Виконується на воркері: розв'язати свою порцію задач."""
        t0 = time.time()
        total = solve_tasks(n, tasks)
        # число передаємо рядком - так серіалізація однакова в Python 2 і 3
        return [str(total), time.time() - t0, len(tasks)]

    @staticmethod
    @expose
    def myreduce(mapped, workers_count):
        """Виконується на master: підсумувати відповіді воркерів."""
        solutions = 0
        busy = [0.0] * workers_count
        done = [0] * workers_count
        for i, value in mapped:
            solutions += int(value[0])
            busy[i] += float(value[1])
            done[i] += int(value[2])
        return solutions, busy, done

    def read_input(self):
        f = open(self.input_file_name, 'r')
        text = f.read()
        f.close()
        return parse_input(text)

    def write_output(self, r):
        lines = [
            "N-Queens (PARCS-Python, parallel)",
            "N = %d" % r['n'],
            "Solutions = %d" % r['solutions'],
            "Expected (OEIS A000170) = %s -> %s" % (
                r['expected'], 'OK' if r['correct'] else 'MISMATCH'),
            "Workers = %d" % r['workers'],
            "Strategy = %s (chunk = %d)" % (r['strategy'], r['chunk']),
            "Decomposition depth = %d, tasks = %d" % (r['depth'], r['tasks']),
            "Total time, s = %.3f" % r['time_total'],
            "  task generation, s = %.3f" % r['time_tasks'],
            "  map (workers), s = %.3f" % r['time_map'],
            "  reduce, s = %.3f" % r['time_reduce'],
            "Worker busy time, s = %s" % ', '.join('%.3f' % b for b in r['worker_busy']),
            "Worker tasks = %s" % ', '.join(str(d) for d in r['worker_tasks']),
            "Load imbalance (max/mean busy) = %.3f" % r['imbalance'],
            "RESULT_JSON " + json.dumps(r, sort_keys=True),
        ]
        f = open(self.output_file_name, 'w')
        f.write('\n'.join(lines))
        f.write('\n')
        f.close()
