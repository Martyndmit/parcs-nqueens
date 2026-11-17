# -*- coding: utf-8 -*-
"""
Послідовний підрахунок кількості розв'язків задачі про N ферзів.

Файл можна запускати двома способами:
  * як задачу ПАРКС (завантажити через веб-інтерфейс разом із вхідним файлом):
    усе обчислення виконується на master, воркери не використовуються;
  * як звичайний скрипт:  python nqueens_sequential.py input/n14.txt [output.txt]

Алгоритм: перебір з поверненням на бітових масках + дзеркальна симетрія
першого рядка (той самий, що й у паралельній версії, але без декомпозиції).
Сумісно з Python 2.7 і Python 3.
"""
from __future__ import division, print_function

import json
import sys
import time

try:
    from Pyro4 import expose
except ImportError:          # запуск без ПАРКС / Pyro4
    def expose(func):
        return func

KNOWN_SOLUTIONS = {
    1: 1, 2: 0, 3: 0, 4: 2, 5: 10, 6: 4, 7: 40, 8: 92, 9: 352, 10: 724,
    11: 2680, 12: 14200, 13: 73712, 14: 365596, 15: 2279184,
    16: 14772512, 17: 95815104, 18: 666090624,
}


def count_completions(full, cols, ld, rd):
    if cols == full:
        return 1
    total = 0
    avail = full & ~(cols | ld | rd)
    while avail:
        bit = avail & -avail
        avail ^= bit
        total += count_completions(full, cols | bit,
                                   ((ld | bit) << 1) & full,
                                   (rd | bit) >> 1)
    return total


def count_nqueens(n):
    """Кількість розв'язків для дошки n x n."""
    full = (1 << n) - 1
    total = 0
    for c in range(n // 2):                       # ліва половина першого рядка, x2
        bit = 1 << c
        total += 2 * count_completions(full, bit, (bit << 1) & full, bit >> 1)
    if n % 2 == 1:                                # середній стовпець, x1
        bit = 1 << (n // 2)
        total += count_completions(full, bit, (bit << 1) & full, bit >> 1)
    return total


def parse_n(text):
    for raw in text.splitlines():
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if '=' in line:
            key, value = [s.strip() for s in line.split('=', 1)]
            if key.lower() == 'n':
                return int(value)
        else:
            return int(line)
    raise ValueError('Input must contain N')


def run(n):
    t0 = time.time()
    solutions = count_nqueens(n)
    elapsed = time.time() - t0
    expected = KNOWN_SOLUTIONS.get(n)
    return {
        'kind': 'sequential', 'n': n, 'workers': 0, 'strategy': 'sequential',
        'solutions': solutions, 'expected': expected,
        'correct': (expected is None) or (solutions == expected),
        'time_total': round(elapsed, 4),
    }


def format_output(r):
    lines = [
        "N-Queens (sequential)",
        "N = %d" % r['n'],
        "Solutions = %d" % r['solutions'],
        "Expected (OEIS A000170) = %s -> %s" % (
            r['expected'], 'OK' if r['correct'] else 'MISMATCH'),
        "Total time, s = %.3f" % r['time_total'],
        "RESULT_JSON " + json.dumps(r, sort_keys=True),
    ]
    return '\n'.join(lines) + '\n'


class Solver:
    """Інтерфейс ПАРКС: обчислення повністю на master, без воркерів."""

    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name
        self.workers = workers
        print("Inited")

    def solve(self):
        print("Job Started (sequential)")
        f = open(self.input_file_name, 'r')
        n = parse_n(f.read())
        f.close()
        result = run(n)
        f = open(self.output_file_name, 'w')
        f.write(format_output(result))
        f.close()
        print("Job Finished")

    @staticmethod
    @expose
    def mymap(*args):
        # не використовується: залишено, щоб воркери ПАРКС могли зареєструвати клас
        return None


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: python nqueens_sequential.py <input.txt> [output.txt]")
        sys.exit(1)
    with open(sys.argv[1]) as fin:
        res = run(parse_n(fin.read()))
    text = format_output(res)
    if len(sys.argv) > 2:
        with open(sys.argv[2], 'w') as fout:
            fout.write(text)
    sys.stdout.write(text)
