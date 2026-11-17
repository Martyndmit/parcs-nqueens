#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматизоване тестування розв'язку в розгорнутому ПАРКС (PARCS-Python).

Скрипт працює через REST API master-вузла:
  GET  /api/worker                     - список воркерів
  POST /api/worker/<id>/<enable|disable> - увімкнути / вимкнути воркер
  POST /api/job                        - надіслати задачу (solution_file, input_file)
  GET  /jobs                           - сторінка задач (звідси беремо id нової задачі)
  GET  /api/job/<id>/output            - вихідний файл (400 - ще виконується)

Для кожної кількості воркерів p вмикає рівно p воркерів, запускає задачу,
чекає завершення й зчитує рядок RESULT_JSON з вихідного файлу.
Результати дописуються в CSV.

Приклад (хмара):
  python3 bench/bench.py --master http://35.228.1.2:8080 --n 15 \
      --workers 1,2,3,4 --repeats 3 --sequential --out results/gcp_n15.csv
Приклад (локальний стенд: python local/parcs_local.py serve --workers 4):
  python3 bench/bench.py --master http://127.0.0.1:8080 --n 14 --workers 1,2

Лише стандартна бібліотека Python 3 - працює й у Google Cloud Shell.
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
import uuid
from urllib import error, request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_FIELDS = ['timestamp', 'kind', 'n', 'strategy', 'depth', 'chunk', 'workers',
              'repeat', 'solutions', 'correct', 'time_total', 'time_map',
              'imbalance', 'worker_busy', 'tasks', 'wall_time', 'job_id']


class Parcs(object):
    def __init__(self, base):
        self.base = base.rstrip('/')

    def _call(self, method, path, data=None, headers=None, timeout=60):
        req = request.Request(self.base + path, data=data, method=method,
                              headers=headers or {})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except error.HTTPError as e:
            return e.code, e.read()

    def workers(self):
        status, body = self._call('GET', '/api/worker')
        if status != 200:
            raise RuntimeError('GET /api/worker -> HTTP %d' % status)
        return sorted(json.loads(body.decode('utf-8'))['workers'], key=lambda w: w['id'])

    def set_worker(self, worker_id, enabled):
        state = 'enable' if enabled else 'disable'
        status, _ = self._call('POST', '/api/worker/%d/%s' % (worker_id, state), data=b'')
        if status != 200:
            raise RuntimeError('POST /api/worker/%d/%s -> HTTP %d' % (worker_id, state, status))

    def job_ids(self):
        status, body = self._call('GET', '/jobs')
        if status != 200:
            raise RuntimeError('GET /jobs -> HTTP %d' % status)
        return set(int(x) for x in re.findall(r'data-job-id="(\d+)"', body.decode('utf-8', 'replace')))

    def job_reason(self, job_id):
        _, body = self._call('GET', '/jobs')
        text = body.decode('utf-8', 'replace')
        m = re.search(r'data-job-id="%d".*?\[reason: ([^\]]*)\]' % job_id, text, re.S)
        return m.group(1) if m else 'unknown'

    def submit(self, name, solution_path, input_bytes):
        boundary = uuid.uuid4().hex
        with open(solution_path, 'rb') as f:
            solution = f.read()
        parts = []
        parts.append(('--%s\r\nContent-Disposition: form-data; name="job_name"\r\n\r\n%s\r\n'
                      % (boundary, name)).encode('utf-8'))
        for field, filename, content in (('solution_file', 'solution.py', solution),
                                         ('input_file', 'input.txt', input_bytes)):
            parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                          'Content-Type: application/octet-stream\r\n\r\n'
                          % (boundary, field, filename)).encode('utf-8'))
            parts.append(content + b'\r\n')
        parts.append(('--%s--\r\n' % boundary).encode('utf-8'))
        before = self.job_ids()
        status, _ = self._call('POST', '/api/job', data=b''.join(parts),
                               headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        if status != 200:
            raise RuntimeError('POST /api/job -> HTTP %d' % status)
        for _ in range(50):
            new = self.job_ids() - before
            if new:
                return max(new)
            time.sleep(0.2)
        raise RuntimeError('submitted job did not appear on /jobs')

    def wait_output(self, job_id, timeout, poll=1.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, body = self._call('GET', '/api/job/%d/output' % job_id)
            if status == 200:
                return body.decode('utf-8', 'replace')
            if status == 404:
                raise RuntimeError('job %d failed: %s' % (job_id, self.job_reason(job_id)))
            time.sleep(poll)
        self._call('DELETE', '/api/job/%d' % job_id)
        raise RuntimeError('job %d timed out after %d s' % (job_id, timeout))


def parse_result(output):
    for line in output.splitlines():
        if line.startswith('RESULT_JSON '):
            return json.loads(line[len('RESULT_JSON '):])
    raise RuntimeError('RESULT_JSON not found in output:\n' + output)


def enable_exactly(parcs, workers, count):
    for i, w in enumerate(workers):
        parcs.set_worker(w['id'], i < count)


def run_one(parcs, args, kind, solution, input_text, workers_on, repeat, writer, csv_file):
    job_name = '%s n=%d p=%d #%d' % (kind, args.n, workers_on, repeat)
    t0 = time.time()
    job_id = parcs.submit(job_name, solution, input_text.encode('utf-8'))
    output = parcs.wait_output(job_id, args.timeout)
    wall = time.time() - t0
    r = parse_result(output)
    row = {
        'timestamp': datetime.datetime.now().isoformat(timespec='seconds'),
        'kind': r['kind'], 'n': r['n'], 'strategy': r.get('strategy', ''),
        'depth': r.get('depth', ''), 'chunk': r.get('chunk', ''),
        'workers': r['workers'] if r['kind'] == 'parallel' else 0,
        'repeat': repeat, 'solutions': r['solutions'], 'correct': r['correct'],
        'time_total': r['time_total'], 'time_map': r.get('time_map', ''),
        'imbalance': r.get('imbalance', ''),
        'worker_busy': ' '.join(str(b) for b in r.get('worker_busy', [])),
        'tasks': r.get('tasks', ''), 'wall_time': round(wall, 3), 'job_id': job_id,
    }
    writer.writerow(row)
    csv_file.flush()
    print('  job #%-4d %-10s %-8s p=%d  T=%8.3f s  wall=%8.3f s  solutions=%d %s'
          % (job_id, row['kind'], row['strategy'], row['workers'], row['time_total'], wall,
             row['solutions'], 'OK' if row['correct'] else 'WRONG'))
    sys.stdout.flush()
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--master', required=True, help='http://<IP master>:8080')
    ap.add_argument('--n', type=int, default=15)
    ap.add_argument('--workers', default='1,2,3,4', help='список p через кому')
    ap.add_argument('--strategies', default='dynamic', help='dynamic,cyclic,block')
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--chunk', type=int, default=1)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--sequential', action='store_true', help='також виміряти послідовну версію')
    ap.add_argument('--timeout', type=int, default=3600, help='тайм-аут однієї задачі, с')
    ap.add_argument('--out', default=os.path.join(ROOT, 'results', 'results.csv'))
    ap.add_argument('--parallel-solution', default=os.path.join(ROOT, 'src', 'nqueens_parallel.py'))
    ap.add_argument('--sequential-solution', default=os.path.join(ROOT, 'src', 'nqueens_sequential.py'))
    args = ap.parse_args()

    parcs = Parcs(args.master)
    workers = parcs.workers()
    counts = [int(x) for x in args.workers.split(',') if x.strip()]
    print('Master %s: %d worker(s) registered' % (args.master, len(workers)))
    if not workers:
        sys.exit('No workers registered - wait for VMs to start and retry.')
    too_many = [c for c in counts if c > len(workers)]
    if too_many:
        print('WARNING: skipping p=%s (only %d workers)' % (too_many, len(workers)))
        counts = [c for c in counts if c <= len(workers)]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    new_file = not os.path.exists(args.out)
    with open(args.out, 'a', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        if new_file:
            writer.writeheader()
        try:
            if args.sequential:
                print('Sequential, n=%d' % args.n)
                enable_exactly(parcs, workers, 1)  # ПАРКС вимагає хоча б одного воркера
                for rep in range(1, args.repeats + 1):
                    run_one(parcs, args, 'seq', args.sequential_solution,
                            'n=%d\n' % args.n, 1, rep, writer, csv_file)
            for strategy in [s.strip() for s in args.strategies.split(',') if s.strip()]:
                text = 'n=%d\ndepth=%d\nstrategy=%s\nchunk=%d\n' % (
                    args.n, args.depth, strategy, args.chunk)
                for p in counts:
                    print('Parallel, n=%d, strategy=%s, p=%d' % (args.n, strategy, p))
                    enable_exactly(parcs, workers, p)
                    for rep in range(1, args.repeats + 1):
                        run_one(parcs, args, 'par', args.parallel_solution,
                                text, p, rep, writer, csv_file)
        finally:
            for w in workers:          # повернути всі воркери в робочий стан
                try:
                    parcs.set_worker(w['id'], True)
                except Exception:
                    pass
    print('Saved to %s' % args.out)


if __name__ == '__main__':
    main()
