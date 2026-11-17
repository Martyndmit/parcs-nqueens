# -*- coding: utf-8 -*-
"""
Локальний стенд, сумісний з PARCS-Python, для налагодження без хмари.

Відтворює те, як ПАРКС виконує розв'язок:
  * на кожному воркері в окремому процесі модуль розв'язку завантажується,
    створюється Solver() і реєструється в Pyro4.Daemon;
  * на master створюються Pyro4-проксі воркерів в асинхронному режимі
    і викликається Solver(workers, input_file, output_file).solve().

Режими:
  run    - виконати одну задачу й надрукувати вихідний файл
           python local/parcs_local.py run --solution src/nqueens_parallel.py \
                  --input input/n13.txt --workers 2
  serve  - підняти HTTP-сервер з тим самим REST API, що й master ПАРКС
           (/api/worker, /api/worker/<id>/<enable|disable>, /api/job, /jobs,
           /api/job/<id>/output), щоб перевірити bench/bench.py локально
           python local/parcs_local.py serve --workers 4 --port 8080

Потрібно: Python 3, pip install Pyro4 flask
"""
import argparse
import importlib.util
import multiprocessing as mp
import os
import queue
import sys
import tempfile
import threading
import time
import traceback

import Pyro4


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def set_async(proxy):
    # у Python 2 / старих Pyro4 функція називається Pyro4.async
    fn = getattr(Pyro4, 'asyncproxy', None) or getattr(Pyro4, 'async')
    fn(proxy)


def _worker_process(solution_path, job_id, index, uri_queue):
    module = load_module(solution_path, 'solver_module_%d_w%d' % (job_id, index))
    daemon = Pyro4.Daemon(host='127.0.0.1')
    uri = daemon.register(module.Solver())
    uri_queue.put((index, str(uri)))
    daemon.requestLoop()


def run_job(solution_path, input_path, output_path, workers, job_id=0):
    """Виконати задачу так, як це робить планувальник ПАРКС."""
    if workers < 1:
        raise RuntimeError('Unable to find workers.')
    ctx = mp.get_context('spawn')
    uri_queue = ctx.Queue()
    procs = [ctx.Process(target=_worker_process,
                         args=(solution_path, job_id, i, uri_queue), daemon=True)
             for i in range(workers)]
    for p in procs:
        p.start()
    proxies = []
    try:
        uris = dict(uri_queue.get(timeout=60) for _ in range(workers))
        for i in range(workers):
            proxy = Pyro4.Proxy(uris[i])
            set_async(proxy)
            proxies.append(proxy)
        module = load_module(solution_path, 'solver_module_%d' % job_id)
        module.Solver(proxies, input_path, output_path).solve()
    finally:
        for proxy in proxies:
            try:
                proxy._pyroRelease()
            except Exception:
                pass
        for p in procs:
            p.terminate()
        for p in procs:
            p.join(5)


# ---------------------------------------------------------------------------
# HTTP-сервер з API master-вузла ПАРКС
# ---------------------------------------------------------------------------
def serve(workers_count, port, host):
    from flask import Flask, Response, jsonify, request, send_from_directory

    app = Flask(__name__)
    home = tempfile.mkdtemp(prefix='parcs_local_')
    workers = [{'id': i, 'ip': '127.0.0.1', 'port': 0, 'enabled': True,
                'info': {'cpu': 'local process', 'ram': '-'}}
               for i in range(workers_count)]
    jobs = []
    jobs_queue = queue.Queue()
    lock = threading.Lock()

    def job_dir(job_id):
        return os.path.join(home, str(job_id))

    def scheduler():
        while True:
            job = jobs_queue.get()
            job['start'] = time.time()
            job['status'] = 'running'
            enabled = sum(1 for w in workers if w['enabled'])
            d = job_dir(job['id'])
            try:
                run_job(os.path.join(d, 'solution.py'), os.path.join(d, 'input.txt'),
                        os.path.join(d, 'output.txt'), enabled, job['id'])
                job['status'] = 'done'
            except Exception as e:
                traceback.print_exc()
                job['status'] = 'failed'
                job['reason'] = str(e) or e.__class__.__name__
            job['duration'] = int(time.time() - job['start'])

    threading.Thread(target=scheduler, daemon=True).start()

    @app.route('/')
    def index():
        return 'PARCS-compatible local stand: %d workers' % len(workers)

    @app.route('/api/worker')
    def api_workers():
        return jsonify(workers=workers)

    @app.route('/api/worker/<int:worker_id>/<state>', methods=['POST'])
    def api_worker_state(worker_id, state):
        for w in workers:
            if w['id'] == worker_id:
                w['enabled'] = (state == 'enable')
                return Response(status=200)
        return Response(status=400)

    @app.route('/api/job', methods=['POST'])
    def api_add_job():
        with lock:
            job = {'id': len(jobs), 'name': (request.form.get('job_name') or '').upper(),
                   'status': 'queued', 'start': None, 'duration': None, 'reason': None}
            jobs.append(job)
        d = job_dir(job['id'])
        os.makedirs(d)
        request.files['solution_file'].save(os.path.join(d, 'solution.py'))
        request.files['input_file'].save(os.path.join(d, 'input.txt'))
        jobs_queue.put(job)
        return '<html>Add Job</html>'

    @app.route('/jobs')
    def jobs_page():
        rows = []
        for j in jobs:
            title = j['name'] + (' [reason: %s]' % j['reason'] if j['status'] == 'failed' else '')
            dur = '' if j['duration'] is None else '0:%d:%d' % divmod(j['duration'], 60)
            rows.append('<div class="job-well" data-job-id="%d">#%d %s %s %s</div>'
                        % (j['id'], j['id'], title, j['status'], dur))
        return '<html><body>%s</body></html>' % '\n'.join(rows)

    @app.route('/api/job/<int:job_id>/<name>')
    def api_job_file(job_id, name):
        if job_id >= len(jobs):
            return Response(status=404)
        job = jobs[job_id]
        files = {'solution': 'solution.py', 'input': 'input.txt', 'output': 'output.txt'}
        if name not in files:
            return Response(status=404)
        if name == 'output' and job['duration'] is None:
            return Response(status=400)
        path = os.path.join(job_dir(job_id), files[name])
        if not os.path.exists(path):
            return Response(status=404)
        return send_from_directory(job_dir(job_id), files[name], as_attachment=True)

    @app.route('/api/job/<int:job_id>', methods=['DELETE'])
    def api_abort(job_id):
        return Response(status=404)

    print('Local PARCS stand: http://%s:%d  (%d workers, job dir %s)'
          % (host, port, workers_count, home))
    app.run(host=host, port=port, threaded=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='mode', required=True)
    r = sub.add_parser('run', help='виконати одну задачу')
    r.add_argument('--solution', required=True)
    r.add_argument('--input', required=True)
    r.add_argument('--workers', type=int, default=2)
    r.add_argument('--output', default=None)
    s = sub.add_parser('serve', help='REST API як у master ПАРКС')
    s.add_argument('--workers', type=int, default=4)
    s.add_argument('--port', type=int, default=8080)
    s.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()

    if args.mode == 'run':
        out = args.output or os.path.join(tempfile.mkdtemp(), 'output.txt')
        t0 = time.time()
        run_job(os.path.abspath(args.solution), os.path.abspath(args.input), out, args.workers)
        with open(out) as f:
            sys.stdout.write(f.read())
        print('(wall time incl. worker start-up: %.2f s)' % (time.time() - t0))
    else:
        serve(args.workers, args.port, args.host)


if __name__ == '__main__':
    main()
