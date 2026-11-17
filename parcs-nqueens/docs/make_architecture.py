import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK='#0b0b0b'; MUTED='#52514e'; EDGE='#8a8984'; ACC='#2a78d6'
W, H = 1000, 540
fig, ax = plt.subplots(figsize=(W/100, H/100), dpi=150)
ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')

def box(x, y, w, h, title, lines, accent=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=10',
                 linewidth=2 if accent else 1.2, edgecolor=ACC if accent else EDGE,
                 facecolor=(0.165, 0.47, 0.84, 0.08) if accent else 'none'))
    ax.text(x + w/2, y + h - 22, title, ha='center', va='center', fontsize=10.5, fontweight='bold', color=INK)
    for i, l in enumerate(lines):
        ax.text(x + 14, y + h - 48 - i*19, l, ha='left', va='center', fontsize=8.6, color=INK)

def arrow(p1, p2):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=11, color=EDGE, linewidth=1.2))

def note(x, y, s, ha='center', size=8.3):
    ax.text(x, y, s, ha=ha, va='center', fontsize=size, color=MUTED)

ax.text(20, 515, 'Master роздає підзадачі, воркери рахують їх паралельно', fontsize=12, fontweight='bold', color=INK, va='center')
note(20, 492, 'ПАРКС-Python у Google Compute Engine: кожен вузол — окрема VM з контейнером hummer12007/parcs-node', ha='left', size=9)

# user
box(20, 300, 180, 110, 'Користувач', ['браузер: UI :8080', 'bench/bench.py', '(REST API)'])
# master
mx, mw, my, mh = 320, 290, 280, 150
box(mx, my, mw, mh, 'VM parcs-master', ['PARCS_ARGS = master',
    'Flask: UI і REST API, порт 8080', 'планувальник задач',
    'solve(): 97 підзадач → воркери', 'myreduce(): сума відповідей'], accent=True)
# workers
wx, ww, wh = 720, 262, 100
wys = [345, 215, 30]
for y, nm in zip(wys, ['VM parcs-worker-1', 'VM parcs-worker-2', 'VM parcs-worker-p']):
    box(wx, y, ww, wh, nm, ['PARCS_ARGS = worker <IP master>', 'Pyro4.Daemon із Solver()', 'mymap(n, tasks)'])
ax.text(wx + ww/2, 165, '⋮', ha='center', va='center', fontsize=18, color=MUTED)

# user <-> master
arrow((200, 372), (320, 372)); note(260, 403, 'solution.py,')
note(260, 388, 'input.txt')
arrow((320, 330), (200, 330)); note(260, 314, 'output.txt')
# master -> workers
for y in wys:
    arrow((mx + mw, my + mh/2), (wx, y + wh/2))
note(665, 446, 'Pyro4 RPC')
note(665, 431, '(async)')
note(665, 416, 'mymap')
# registration (worker -> master), dashed
ax.add_patch(FancyArrowPatch((wx, 50), (mx + mw/2, my), arrowstyle='-|>', mutation_scale=11,
             color=EDGE, linewidth=1.0, linestyle='--', connectionstyle='angle3,angleA=180,angleB=90'))
note(452, 250, 'реєстрація воркера і heartbeat', ha='right')
note(452, 235, '(HTTP, внутрішня IP master)', ha='right')
# footer
note(20, 70, 'Кожна VM: n1-standard-1 (1 vCPU),', ha='left', size=8.8)
note(20, 53, 'Container-Optimized OS; startup-script:', ha='left', size=8.8)
note(20, 36, 'docker run --network host parcs-node', ha='left', size=8.8)
fig.tight_layout(pad=0.2)
fig.savefig('docs/architecture.png')
