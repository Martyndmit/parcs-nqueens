#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерація PDF-звіту до лабораторної роботи (Завдання 1, ПАРКС) з даних у results/.

  pip install reportlab matplotlib
  python3 docs/build_report.py                       # -> report/Lab1_PARCS_NQueens.pdf
  python3 docs/build_report.py --github https://github.com/<login>/parcs-nqueens

Таблиці й числа в тексті беруться з CSV:
  results/local_n15.csv        - локальний стенд
  results/simulation_n15*.csv  - модель балансування
  results/gcp_n15.csv          - заміри в Google Cloud (якщо файл є, розділ 10 заповнюється сам)
"""
import argparse
import csv
import datetime
import os
import statistics
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bench'))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph,  # noqa: E402
                                Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.doctemplate import BaseDocTemplate, PageTemplate  # noqa: E402
from reportlab.platypus.frames import Frame  # noqa: E402
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

# ---------------------------------------------------------------------------
# Титульні дані (можна змінити тут або аргументами командного рядка)
# ---------------------------------------------------------------------------
STUDENT = 'Мартиненко Дмитро Костянтинович'
GROUP = 'ТК-41'
TEACHER = "Дерев'янченко О. В."
GITHUB = 'https://github.com/<login>/parcs-nqueens'
N = 15

# ---------------------------------------------------------------------------
# Шрифти: Times New Roman / Liberation Serif / FreeSerif / DejaVu Serif
# ---------------------------------------------------------------------------
SERIF_CANDIDATES = [
    ('C:/Windows/Fonts/times.ttf', 'C:/Windows/Fonts/timesbd.ttf', 'C:/Windows/Fonts/timesi.ttf'),
    ('/Library/Fonts/Times New Roman.ttf', '/Library/Fonts/Times New Roman Bold.ttf',
     '/Library/Fonts/Times New Roman Italic.ttf'),
    ('/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
     '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf'),
    ('/usr/share/fonts/truetype/freefont/FreeSerif.ttf',
     '/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf',
     '/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
     '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
     '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf'),
]
MONO_CANDIDATES = [
    'C:/Windows/Fonts/consola.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
    '/usr/share/fonts/truetype/freefont/FreeMono.ttf',
]


def register_fonts():
    for regular, bold, italic in SERIF_CANDIDATES:
        if all(os.path.exists(p) for p in (regular, bold, italic)):
            pdfmetrics.registerFont(TTFont('Serif', regular))
            pdfmetrics.registerFont(TTFont('Serif-Bold', bold))
            pdfmetrics.registerFont(TTFont('Serif-Italic', italic))
            pdfmetrics.registerFontFamily('Serif', normal='Serif', bold='Serif-Bold',
                                          italic='Serif-Italic', boldItalic='Serif-Bold')
            break
    else:
        sys.exit('No Cyrillic serif font found (install fonts-liberation or fonts-dejavu)')
    for mono in MONO_CANDIDATES:
        if os.path.exists(mono):
            pdfmetrics.registerFont(TTFont('Mono', mono))
            break
    else:
        sys.exit('No monospace font found')


# ---------------------------------------------------------------------------
# Стилі (ДСТУ 3008: 14 pt, міжрядковий 1,5, абзацний відступ 1,25 см)
# ---------------------------------------------------------------------------
def make_styles():
    s = {}
    s['body'] = ParagraphStyle('body', fontName='Serif', fontSize=14, leading=21,
                               alignment=TA_JUSTIFY, firstLineIndent=12.5 * mm, spaceAfter=0)
    s['body_ni'] = ParagraphStyle('body_ni', parent=s['body'], firstLineIndent=0)
    s['bullet'] = ParagraphStyle('bullet', parent=s['body'], firstLineIndent=0,
                                 leftIndent=12.5 * mm, bulletIndent=5 * mm)
    s['bullet_l'] = ParagraphStyle('bullet_l', parent=s['bullet'], alignment=TA_LEFT)
    s['lead'] = ParagraphStyle('lead', parent=s['body'], keepWithNext=1)
    s['h1'] = ParagraphStyle('h1', fontName='Serif-Bold', fontSize=14, leading=21,
                             alignment=TA_LEFT, firstLineIndent=12.5 * mm,
                             spaceBefore=14, spaceAfter=8, keepWithNext=1)
    s['h1c'] = ParagraphStyle('h1c', parent=s['h1'], alignment=TA_CENTER, firstLineIndent=0)
    s['cap_fig'] = ParagraphStyle('cap_fig', fontName='Serif', fontSize=12, leading=16,
                                  alignment=TA_CENTER, spaceBefore=4, spaceAfter=10)
    s['cap_tab'] = ParagraphStyle('cap_tab', fontName='Serif', fontSize=12, leading=16,
                                  alignment=TA_LEFT, spaceBefore=8, spaceAfter=4, keepWithNext=1)
    s['cell'] = ParagraphStyle('cell', fontName='Serif', fontSize=11.5, leading=14, alignment=TA_LEFT)
    s['cellc'] = ParagraphStyle('cellc', parent=s['cell'], alignment=TA_CENTER)
    s['cellh'] = ParagraphStyle('cellh', parent=s['cell'], fontName='Serif-Bold', alignment=TA_CENTER)
    s['code'] = ParagraphStyle('code', fontName='Mono', fontSize=9, leading=11.5,
                               backColor=colors.HexColor('#f4f3f0'), borderPadding=(5, 6, 5, 6),
                               spaceBefore=8, spaceAfter=10, leftIndent=4, rightIndent=4)
    s['listing'] = ParagraphStyle('listing', fontName='Mono', fontSize=8.2, leading=10.2)
    s['title_c'] = ParagraphStyle('title_c', fontName='Serif', fontSize=14, leading=20, alignment=TA_CENTER)
    s['title_b'] = ParagraphStyle('title_b', parent=s['title_c'], fontName='Serif-Bold', fontSize=16, leading=24)
    s['title_r'] = ParagraphStyle('title_r', parent=s['title_c'], alignment=TA_LEFT, leftIndent=85 * mm)
    s['toc0'] = ParagraphStyle('toc0', fontName='Serif', fontSize=14, leading=21, leftIndent=0)
    s['note'] = ParagraphStyle('note', parent=s['body'], fontName='Serif-Italic', fontSize=12, leading=17)
    return s


# ---------------------------------------------------------------------------
# Документ із нумерацією сторінок і змістом
# ---------------------------------------------------------------------------
class ReportDoc(BaseDocTemplate):
    def __init__(self, path, **kw):
        super().__init__(path, pagesize=A4, leftMargin=30 * mm, rightMargin=15 * mm,
                         topMargin=20 * mm, bottomMargin=20 * mm, **kw)
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id='f')
        self.addPageTemplates([PageTemplate(id='p', frames=[frame], onPage=self._page_number)])

    @staticmethod
    def _page_number(canvas, doc):
        if doc.page > 1:
            canvas.saveState()
            canvas.setFont('Serif', 12)
            canvas.drawCentredString(A4[0] / 2 + 7.5 * mm, 10 * mm, str(doc.page))
            canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, 'toc_level', None) is not None:
            text = getattr(flowable, 'toc_text', None) or flowable.getPlainText()
            key = 'h%d' % id(flowable)
            self.canv.bookmarkPage(key)
            self.notify('TOCEntry', (flowable.toc_level, text, self.page, key))


# ---------------------------------------------------------------------------
# Дані
# ---------------------------------------------------------------------------
def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def summarize(rows, n):
    seq = [float(r['time_total']) for r in rows if r['kind'] == 'sequential' and int(r['n']) == n]
    par, imb, correct = {}, {}, []
    for r in rows:
        if int(r['n']) != n:
            continue
        correct.append(r['correct'] in ('True', 'true', '1'))
        if r['kind'] == 'parallel':
            key = (r['strategy'], int(r['workers']))
            par.setdefault(key, []).append(float(r['time_total']))
            if r['imbalance']:
                imb.setdefault(key, []).append(float(r['imbalance']))
    t_seq = statistics.median(seq) if seq else None
    table = {}
    for key, times in par.items():
        t = statistics.median(times)
        s = (t_seq / t) if t_seq else None
        table[key] = {'runs': len(times), 'time': t, 'min': min(times), 'max': max(times),
                      'speedup': s, 'eff': (s / key[1]) if s else None,
                      'imb': statistics.median(imb[key]) if key in imb else None}
    return {'t_seq': t_seq, 'seq_runs': len(seq), 'table': table,
            'runs': len(correct), 'all_correct': all(correct) if correct else False}


def f2(x, digits=2):
    return ('%.*f' % (digits, x)).replace('.', ',')


def runs_word(n):
    if n % 10 == 1 and n % 100 != 11:
        return 'запуск'
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 'запуски'
    return 'запусків'


def esc(text):
    return escape(text)


def code(text):
    return '<font face="Mono" size="11.5">%s</font>' % esc(text)


# ---------------------------------------------------------------------------
# Формули (matplotlib mathtext -> PNG)
# ---------------------------------------------------------------------------
def formula_image(tex, path, width_mm, fontsize=15):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams['mathtext.fontset'] = 'stix'
    fig = plt.figure(figsize=(0.01, 0.01), dpi=300)
    fig.text(0, 0, '$%s$' % tex, fontsize=fontsize)
    fig.savefig(path, dpi=300, bbox_inches='tight', pad_inches=0.04, transparent=True)
    plt.close(fig)
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(path).getSize()
    width = min(width_mm * mm, w / 300 * 72)
    return Image(path, width=width, height=width * h / w)


def picture(path, width_mm, max_height_mm=None):
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(path).getSize()
    width = width_mm * mm
    height = width * h / w
    if max_height_mm and height > max_height_mm * mm:
        height = max_height_mm * mm
        width = height * w / h
    return Image(path, width=width, height=height)


# ---------------------------------------------------------------------------
# Побудова звіту
# ---------------------------------------------------------------------------
class Builder(object):
    def __init__(self, args):
        self.a = args
        self.s = make_styles()
        self.story = []
        self.fig_no = 0
        self.tab_no = 0
        self.tmp = os.path.join(ROOT, 'report', '.build')
        os.makedirs(self.tmp, exist_ok=True)

    # --- примітиви ---
    def p(self, text, style='body'):
        self.story.append(Paragraph(text, self.s[style]))

    def h(self, text, level=0, centered=False, toc_text=None):
        para = Paragraph(text, self.s['h1c' if centered else 'h1'])
        para.toc_level = level
        para.toc_text = toc_text
        self.story.append(para)

    def bullets(self, items, numbered=False, style='bullet'):
        for i, item in enumerate(items, 1):
            bullet = '%d)' % i if numbered else '–'
            self.story.append(Paragraph(item, self.s[style], bulletText=bullet))

    def code_block(self, text):
        self.story.append(Preformatted(text.rstrip('\n'), self.s['code'], maxLineLength=86))

    def figure(self, path, caption, width_mm=160, max_height_mm=110):
        self.fig_no += 1
        img = picture(path, width_mm, max_height_mm)
        cap = Paragraph('Рисунок %d – %s' % (self.fig_no, caption), self.s['cap_fig'])
        self.story.append(KeepTogether([Spacer(1, 4), img, cap]))

    def table(self, caption, header, rows, col_widths_mm, align_center_from=1, note=None):
        self.tab_no += 1
        data = [[Paragraph(hc, self.s['cellh']) for hc in header]]
        for row in rows:
            data.append([Paragraph(str(c), self.s['cellc'] if j >= align_center_from else self.s['cell'])
                         for j, c in enumerate(row)])
        t = Table(data, colWidths=[w * mm for w in col_widths_mm], repeatRows=1)
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        block = [Paragraph('Таблиця %d – %s' % (self.tab_no, caption), self.s['cap_tab']), t]
        if note:
            block.append(Spacer(1, 4))
            block.append(Paragraph(note, self.s['note']))
        block.append(Spacer(1, 8))
        self.story.append(KeepTogether(block))

    # --- сторінки ---
    def title_page(self):
        s = self.s
        st = self.story
        st.append(Paragraph('КИЇВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ<br/>ІМЕНІ ТАРАСА ШЕВЧЕНКА', s['title_c']))
        st.append(Spacer(1, 6))
        st.append(Paragraph("Факультет комп'ютерних наук та кібернетики", s['title_c']))
        st.append(Spacer(1, 50 * mm))
        st.append(Paragraph('ЗВІТ', s['title_b']))
        st.append(Paragraph('до лабораторної роботи (завдання 1)<br/>з дисципліни «Хмарні обчислення»',
                            s['title_c']))
        st.append(Spacer(1, 10))
        st.append(Paragraph('на тему: «Паралельний підрахунок кількості розв\'язків задачі про N ферзів '
                            'у системі ПАРКС-Python з розгортанням у Google Cloud»', s['title_c']))
        st.append(Spacer(1, 30 * mm))
        st.append(Paragraph('Виконав:<br/>студент групи %s<br/>%s' % (esc(self.a.group), esc(self.a.student)),
                            s['title_r']))
        st.append(Spacer(1, 10))
        st.append(Paragraph('Перевірив:<br/>%s' % esc(self.a.teacher), s['title_r']))
        st.append(Spacer(1, 28 * mm))
        st.append(Paragraph('Київ – %d' % datetime.date.today().year, s['title_c']))
        st.append(PageBreak())

    def toc_page(self):
        self.story.append(Paragraph('ЗМІСТ', self.s['h1c']))
        toc = TableOfContents()
        toc.levelStyles = [self.s['toc0']]
        toc.dotsMinLevel = 0
        self.story.append(toc)
        self.story.append(PageBreak())

    # --- розділи ---
    def build(self):
        local = summarize(read_csv(os.path.join(ROOT, 'results', 'local_n%d.csv' % N)), N)
        sim = read_csv(os.path.join(ROOT, 'results', 'simulation_n%d.csv' % N))
        tasks = read_csv(os.path.join(ROOT, 'results', 'simulation_n%d_tasks.csv' % N))
        gcp_rows = read_csv(os.path.join(ROOT, 'results', 'gcp_n%d.csv' % N))
        gcp = summarize(gcp_rows, N) if gcp_rows else None

        self.title_page()
        self.toc_page()
        self.sec_goal()
        self.sec_problem(local)
        self.sec_parcs()
        self.sec_sequential()
        self.sec_parallel(tasks)
        self.sec_deploy()
        self.sec_method()
        self.sec_local(local)
        self.sec_model(sim, tasks)
        self.sec_gcp(gcp)
        self.sec_conclusions(local, sim, gcp)
        self.sec_sources()
        self.app_guide()
        self.app_listings()

        out_dir = os.path.join(ROOT, 'report')
        out = os.path.join(out_dir, self.a.output)
        doc = ReportDoc(out, title='Лабораторна робота 1. ПАРКС: задача про N ферзів',
                        author=self.a.student)
        doc.multiBuild(self.story)
        return out

    def sec_goal(self):
        self.h('1 МЕТА ТА ЗАВДАННЯ')
        self.p('<b>Мета роботи</b> – реалізувати паралельний алгоритм у системі ПАРКС, розгорнути ПАРКС '
               'у хмарному середовищі та оцінити прискорення відносно послідовного алгоритму для різної '
               'кількості воркерів.')
        self.p('Завдання роботи:')
        self.bullets([
            'обрати задачу паралельного програмування та платформу ПАРКС – обрано задачу про N ферзів '
            'і ПАРКС-Python;',
            'розгорнути ПАРКС у хмарному середовищі – обрано Google Compute Engine;',
            'протестувати послідовний і паралельний алгоритми для різної кількості воркерів;',
            'оформити звіт з описом алгоритмів і порівнянням результатів, код завантажити на github.com.',
        ], numbered=True)

    def sec_problem(self, local):
        self.h('2 ПОСТАНОВКА ЗАДАЧІ')
        self.p("Потрібно знайти кількість Q(N) усіх розстановок N ферзів на шаховій дошці N × N, у яких "
               "жоден ферзь не б'є іншого: у кожному рядку, стовпці та на кожній діагоналі стоїть не більше "
               "одного ферзя.")
        t_seq = local['t_seq']
        self.p("Закритої формули для Q(N) немає, тому розв'язки перебираються. Час перебору зростає "
               "приблизно в 6–7 разів при збільшенні N на одиницю: на тестовому стенді послідовна версія "
               "рахує N = 14 приблизно за 3,3 с, а N = 15 – за %s с." % f2(t_seq))
        self.p('Задача добре підходить для розподілених обчислень у ПАРКС:', 'lead')
        self.bullets([
            "дерево перебору розпадається на незалежні піддерева, тому воркерам не потрібно "
            "обмінюватися даними між собою;",
            "обсяг передачі мінімальний: підзадача – три цілі числа, відповідь – одне число;",
            "результат перевіряється за відомою послідовністю OEIS A000170: Q(14) = 365 596, "
            "Q(15) = 2 279 184, Q(16) = 14 772 512.",
        ])

    def sec_parcs(self):
        self.h('3 СИСТЕМА ПАРКС-PYTHON')
        self.p('ПАРКС-Python – система розподілених обчислень за схемою «master – workers», у якій виклики '
               'між вузлами виконуються через бібліотеку Pyro4 (Python Remote Objects). Кожен вузол – '
               'Docker-контейнер %s (Python 2.7, Flask, Pyro4); роль вузла задає змінна середовища '
               '%s: %s або %s.' % (code('hummer12007/parcs-node'), code('PARCS_ARGS'),
                                   code('master'), code('worker <IP master>')))
        self.p('Задача виконується так:', 'lead')
        self.bullets([
            'воркер після старту реєструється на master через HTTP і далі надсилає heartbeat;',
            "користувач через веб-інтерфейс (порт 8080) або REST API надсилає файл розв'язку "
            "(.py) і вхідний файл;",
            "планувальник master розсилає файл розв'язку всім увімкненим воркерам; кожен воркер "
            "завантажує модуль, створює об'єкт %s, реєструє його в %s і повертає URI;"
            % (code('Solver()'), code('Pyro4.Daemon')),
            'master створює Pyro4-проксі воркерів в асинхронному режимі й викликає '
            '%s;' % code('Solver(workers, input_file, output_file).solve()'),
            'виклик %s одразу повертає %s, тож усі воркери рахують одночасно, а читання %s '
            'чекає на відповідь;' % (code('workers[i].mymap(...)'), code('FutureResult'), code('.value')),
            'результат записується у вихідний файл, доступний на сторінці Jobs.',
        ], numbered=True)
        self.figure(os.path.join(ROOT, 'docs', 'architecture.png'),
                    'Архітектура розгортання ПАРКС-Python у Google Compute Engine', 165, 95)
        self.p("Інтерфейс розв'язку – клас %s із конструктором %s, методом %s для master і статичними "
               "методами з декоратором %s, які викликаються на воркерах. Розв'язок має працювати в "
               "Python 2.7, а аргументи й результати викликів серіалізуються бібліотекою serpent "
               "(списки, рядки, числа)." % (code('Solver'), code('(workers, input_file_name, output_file_name)'),
                                            code('solve()'), code('@expose')))

    def sec_sequential(self):
        self.h('4 ПОСЛІДОВНИЙ АЛГОРИТМ')
        self.p('Послідовний алгоритм – перебір з поверненням (backtracking) по рядках дошки, у якому стан '
               'зберігається в трьох бітових масках (файл %s):' % code('src/nqueens_sequential.py'))
        self.bullets([
            '%s – зайняті стовпці;' % code('cols'),
            "%s, %s – клітинки поточного рядка, які б'ються по діагоналях; при переході до наступного "
            "рядка вони зсуваються на один біт ліворуч і праворуч;" % (code('ld'), code('rd')),
            'вільні клітинки рядка: %s, де %s – маска з N одиниць;'
            % (code('avail = full & ~(cols | ld | rd)'), code('full')),
            'наймолодший вільний стовпець виділяється як %s, тому недопустимі клітинки взагалі '
            'не перебираються.' % code('avail & -avail'),
        ])
        self.p("Додатково використано дзеркальну симетрію: розв'язки з ферзем першого рядка в правій половині "
               "дошки є дзеркальними копіями розв'язків з лівої половини. Тому перебирається лише ліва "
               "половина, а для непарного N – ще й середній стовпець, що зменшує обсяг роботи приблизно "
               "вдвічі:")
        self.story.append(Spacer(1, 4))
        self.story.append(formula_image(
            r"Q(N) = 2\sum_{c=0}^{\lfloor N/2\rfloor-1} Q_c(N) + [N\ \mathrm{mod}\ 2 = 1]\cdot Q_{\lfloor N/2\rfloor}(N),",
            os.path.join(self.tmp, 'f1.png'), 120))
        self.p("де Q<sub>c</sub>(N) – кількість розв'язків із ферзем першого рядка у стовпці c.", 'body_ni')
        self.code_block('''def count_completions(full, cols, ld, rd):
    if cols == full:                    # усі N ферзів розставлено
        return 1
    total = 0
    avail = full & ~(cols | ld | rd)    # вільні клітинки поточного рядка
    while avail:
        bit = avail & -avail            # наймолодший вільний стовпець
        avail ^= bit
        total += count_completions(full, cols | bit,
                                   ((ld | bit) << 1) & full, (rd | bit) >> 1)
    return total''')
        self.p('У найгіршому випадку складність обмежена O(N!), але відсікання по діагоналях значно '
               "зменшує дерево перебору. Пам'ять – O(N) на стек рекурсії.")

    def sec_parallel(self, tasks):
        self.h('5 ПАРАЛЕЛЬНИЙ АЛГОРИТМ')
        n_tasks = len(tasks) or 97
        self.p('Паралельний алгоритм ділить дерево перебору на незалежні підзадачі на master, роздає їх '
               'воркерам (map) і підсумовує відповіді (reduce). Файл – %s.' % code('src/nqueens_parallel.py'))
        self.p('<b>Декомпозиція.</b> Master перебирає всі коректні розстановки ферзів у перших depth рядках '
               '(за замовчуванням depth = 2) з урахуванням симетрії першого рядка. Кожен префікс – окрема '
               'підзадача вигляду %s, де вага 2 враховує дзеркальну копію. Для N = 13, 14, 15, 16 '
               'виходить 71, 78, 97 і 105 підзадач відповідно.' % code('[вага, c0, c1]'))
        if tasks:
            secs = [float(r['seconds']) for r in tasks]
            self.p('Для N = %d глибина 2 дає від %d підзадач на воркер при p = 1 до %d при p = 8 – '
                   'достатньо для балансування. Підзадача рахується в середньому %s с, а один '
                   'RPC-виклик коштує близько 2 мс, тобто накладні витрати – близько 1 %%.'
                   % (N, n_tasks, -(-n_tasks // 8), f2(statistics.mean(secs), 2)))
        self.p('<b>Розподіл підзадач</b> задається у вхідному файлі параметром %s (табл. 1).' % code('strategy'))
        self.table('Стратегії розподілу підзадач між воркерами',
                   ['Стратегія', 'Як працює', 'RPC-викликів', 'Балансування'],
                   [['block', 'воркер i отримує суцільний блок задач', 'p',
                     'статичне; сусідні задачі мають схожу вартість, тому блоки нерівні'],
                    ['cyclic', 'задача k передається воркеру k mod p (round-robin)', 'p',
                     'статичне; дорогі й дешеві задачі перемішуються'],
                    ['dynamic', '«мішок задач»: наступну порцію отримує воркер, що звільнився першим',
                     'кількість порцій', 'динамічне; витримує і нерівні задачі, і повільні VM']],
                   [27, 55, 30, 53], align_center_from=2)
        self.p('<b>Map.</b> Метод %s виконується на воркері: відновлює бітові маски для кожного префікса, '
               'рахує доповнення тією ж функцією %s і повертає %s. Кількість передається рядком, щоб '
               'серіалізація була однаковою в Python 2 і 3.'
               % (code('mymap(n, tasks)'), code('count_completions'), code('[кількість, час, число задач]')))
        self.p('<b>Reduce.</b> Метод %s на master підсумовує кількості та час роботи кожного воркера; з них '
               'рахується дисбаланс навантаження (розділ 7).' % code('myreduce'))
        self.p('Динамічний розподіл на master:', 'lead')
        self.code_block('''queue = [tasks[i:i + chunk] for i in range(0, len(tasks), chunk)]
queue.reverse()
pending = {i: self.workers[i].mymap(n, queue.pop()) for i in range(p)}   # async
while pending:
    for i in list(pending):
        if pending[i].ready:                          # FutureResult готовий
            mapped.append((i, pending[i].value))
            if queue:
                pending[i] = self.workers[i].mymap(n, queue.pop())
            else:
                del pending[i]
    time.sleep(0.001)''')
        self.p('Опитування %s з паузою 1 мс обрано замість %s: у Python 2.7 очікування з тайм-аутом '
               'реалізоване через sleep до 50 мс і додавало б затримку на кожну порцію.'
               % (code('ready'), code('Event.wait(timeout)')))

    def sec_deploy(self):
        self.h('6 РОЗГОРТАННЯ ПАРКС У GOOGLE CLOUD')
        self.p('ПАРКС розгортається скриптом %s: master і N воркерів на VM %s (1 vCPU, 3,75 ГБ) у зоні %s, '
               'як у методичних рекомендаціях.' % (code('deploy/gcp/deploy.sh'), code('n1-standard-1'),
                                                   code('europe-north1-a')))
        self.p('<b>Зміна відносно методичних рекомендацій.</b> Методичка створює VM командою %s. Google '
               'вимкнув цей механізм (container startup agent) 31 липня 2026 року [7], тому команда більше '
               'не запускає контейнер. Замість неї використано рекомендований Google спосіб [8]: образ '
               'Container-Optimized OS (%s) і startup-script, який запускає контейнер командою %s.'
               % (code('gcloud compute instances create-with-container'), code('cos-stable'),
                  code('docker run')))
        self.p('Кроки скрипта:', 'lead')
        self.bullets([
            'увімкнути Compute Engine API в обраному проєкті;',
            'створити правила брандмауера: %s – увесь трафік між VM з тегом %s (реєстрація воркерів, '
            'HTTP API, Pyro4 на випадкових портах) і %s – TCP 8080 до master (веб-інтерфейс і REST API);'
            % (code('parcs-allow-internal'), code('parcs'), code('parcs-allow-ui')),
            'створити master з метаданими %s і дізнатися його внутрішню та зовнішню IP-адреси;'
            % code('parcs-args=master'),
            'створити воркери з метаданими %s;' % code('parcs-args=worker <внутрішній IP master>'),
            'дочекатися, поки всі воркери зареєструються (%s).' % code('GET /api/worker'),
        ], numbered=True)
        self.p('Startup-script (%s) на кожній VM читає роль із сервера метаданих, відкриває вхідні '
               "з'єднання в iptables (Container-Optimized OS блокує їх за замовчуванням) і запускає "
               'контейнер:' % code('deploy/gcp/startup.sh'))
        self.code_block('''PARCS_ARGS="$(curl -sf -H 'Metadata-Flavor: Google' "$MD/parcs-args")"
iptables -w -A INPUT -j ACCEPT
docker pull hummer12007/parcs-node
docker run -d --name parcs --network host --restart always \\
  -e PARCS_ARGS="$PARCS_ARGS" hummer12007/parcs-node''')
        self.p('Мережа хоста (%s) потрібна, бо воркер визначає свою адресу через %s і відкриває Pyro4 на '
               'випадковому порту – так само працював контейнер у %s. У пробному періоді GCP одночасно '
               'доступно не більше 8 ядер [9], тобто master і до 7 воркерів %s. Покрокова інструкція '
               'запуску наведена в додатку А.'
               % (code('--network host'), code('hostname -I'), code('create-with-container'),
                  code('n1-standard-1')))

    def sec_method(self):
        self.h('7 МЕТОДИКА ТЕСТУВАННЯ')
        self.p('Основний експеримент – N = %d (97 підзадач): послідовна версія і паралельна для p = 1, 2, 3, 4 '
               'воркерів, по 3 запуски на конфігурацію; у таблицях наведено медіану.' % N)
        self.p('Метрики:', 'lead')
        self.story.append(formula_image(
            r"S_p = \dfrac{T_{seq}}{T_p},\qquad E_p = \dfrac{S_p}{p},\qquad "
            r"D_p = \dfrac{\max_i\, B_i}{(1/p)\,\sum_{i=1}^{p} B_i},",
            os.path.join(self.tmp, 'f2.png'), 130, fontsize=16))
        self.p('де T<sub>seq</sub> – час послідовної версії, T<sub>p</sub> – час паралельної на p воркерах, '
               'B<sub>i</sub> – час зайнятості воркера i, S – прискорення, E – ефективність, D – дисбаланс '
               'навантаження (1,0 – ідеально рівномірний розподіл).', 'body_ni')
        self.p('Час вимірюється всередині %s через %s – від читання вхідного файлу до отримання всіх '
               'відповідей, з точністю до мілісекунд. Веб-інтерфейс ПАРКС показує тривалість лише в цілих '
               'секундах і включає запуск RPC на воркерах, тому для порівняння використовується власний '
               'замір. Усі числа записуються у вихідний файл рядком %s.'
               % (code('solve()'), code('time.time()'), code('RESULT_JSON')))
        self.p('Запуски автоматизовані скриптом %s через REST API master: для кожного p він вмикає рівно p '
               'воркерів (%s), надсилає задачу (%s), чекає на вихідний файл (%s) і зберігає рядок CSV. '
               "Послідовна версія запускається як задача ПАРКС і рахує на master, щоб усі версії "
               "виконувалися на однакових VM."
               % (code('bench/bench.py'), code('POST /api/worker/<id>/disable'), code('POST /api/job'),
                  code('GET /api/job/<id>/output')))

    def sec_local(self, local):
        self.h('8 РЕЗУЛЬТАТИ НА ЛОКАЛЬНОМУ СТЕНДІ')
        tab = local['table']
        d2 = tab.get(('dynamic', 2))
        self.p('Перед запуском у хмарі код і скрипти перевірено на локальному стенді. Конфігурація: VM з '
               '2 vCPU (Intel Xeon 2,1 ГГц), 7 ГБ RAM, Ubuntu 24.04, Python 3.11, Pyro4 4.82. Скрипт %s '
               'відтворює механіку ПАРКС: кожен воркер – окремий процес з %s, master викликає %s з '
               'асинхронними проксі, а REST API збігається з API master ПАРКС, тож %s працює з ним без змін.'
               % (code('local/parcs_local.py'), code('Pyro4.Daemon'), code('solve()'), code('bench.py')))
        self.p("Усі %d %s повернули Q(%d) = 2 279 184, що збігається з OEIS. Послідовна версія: "
               "T<sub>seq</sub> = %s с (медіана з %d запусків). Результати паралельної версії – у табл. 2 "
               "і на рис. 2." % (local['runs'], runs_word(local['runs']), N, f2(local['t_seq']),
                                 local['seq_runs']))
        rows = []
        for key in sorted(tab, key=lambda k: (k[0] != 'dynamic', k[0] == 'block', k[1])):
            r = tab[key]
            rows.append([key[0], key[1], f2(r['time']), '%s–%s' % (f2(r['min']), f2(r['max'])),
                         f2(r['speedup']), f2(r['eff']), f2(r['imb'], 3) if r['imb'] else '–'])
        self.table('Час і прискорення на локальному стенді (2 vCPU), N = %d' % N,
                   ['Стратегія', 'p', 'T<sub>p</sub>, с', 'min–max, с', 'S', 'E', 'D'],
                   rows, [26, 12, 24, 36, 20, 20, 27], align_center_from=1)
        self.figure(os.path.join(ROOT, 'results', 'local_n%d_speedup.png' % N),
                    'Прискорення на локальному стенді (2 vCPU), N = %d' % N, 150, 95)
        d1 = tab.get(('dynamic', 1))
        items = []
        if d1:
            items.append('при p = 1 накладні витрати ПАРКС становлять близько %d %% (97 RPC-викликів, '
                         'серіалізація, опитування готовності);' % round((d1['time'] / local['t_seq'] - 1) * 100))
        if d2:
            items.append('при p = 2 прискорення дорівнює %s, ефективність – %s;' % (f2(d2['speedup']), f2(d2['eff'])))
        hi = [tab[k]['speedup'] for k in tab if k[0] == 'dynamic' and k[1] > 2]
        if hi:
            items.append('при p = 3, 4 прискорення не перевищує %s, бо воркери ділять два ядра; тому в хмарі '
                         'кожен воркер розміщується на окремій VM;' % f2(max(hi)))
        b2, c2 = tab.get(('block', 2)), tab.get(('cyclic', 2))
        if b2 and c2 and d2:
            items.append('при p = 2 стратегія block має помітний дисбаланс (%s), у cyclic і dynamic він не '
                         'перевищує %s; різниця часу між cyclic і dynamic – у межах розкиду запусків.'
                         % (f2(b2['imb'], 3), f2(max(c2['imb'], d2['imb']), 3)))
        self.p('Висновки з локального тестування:', 'lead')
        self.bullets(items)

    def sec_model(self, sim, tasks):
        self.h('9 МОДЕЛЬ БАЛАНСУВАННЯ НАВАНТАЖЕННЯ')
        if not sim or not tasks:
            self.p('Дані моделювання відсутні (запустіть bench/simulate_balance.py).')
            return
        secs = [float(r['seconds']) for r in tasks]
        get = {(int(r['p']), r['strategy']): r for r in sim}
        max_p = max(p for p, _ in get)
        self.p('На двох ядрах стенду вплив стратегії розподілу для 4–8 воркерів не виміряти, тому виконано '
               'моделювання (%s):' % code('bench/simulate_balance.py'))
        self.bullets([
            'час кожної з %d підзадач N = %d виміряно окремо (мінімум із 3 вимірювань): від %s до %s с, '
            'у середньому %s с, разом %s с;' % (len(secs), N, f2(min(secs), 3), f2(max(secs), 3),
                                              f2(statistics.mean(secs), 3), f2(sum(secs))),
            'для p = 1…%d задачі розподіляються за кожною стратегією між ідеальними воркерами без мережевих '
            'витрат; dynamic моделюється як «наступна задача – першому вільному воркеру»;' % max_p,
            'прискорення = сумарний час / час найдовшого воркера.',
        ], numbered=True)
        rows = []
        for p in (2, 4, 6, 8):
            if (p, 'block') not in get:
                continue
            row = [p]
            for s in ('block', 'cyclic', 'dynamic'):
                r = get[(p, s)]
                row.append('%s / %s' % (f2(float(r['speedup'])), f2(float(r['imbalance']), 3)))
            rows.append(row)
        self.table('Модельне прискорення S і дисбаланс D за стратегіями, N = %d' % N,
                   ['p', 'block: S / D', 'cyclic: S / D', 'dynamic: S / D'], rows, [20, 48, 48, 49])
        self.figure(os.path.join(ROOT, 'results', 'simulation_n%d.png' % N),
                    'Модельне прискорення для p = 1…%d за виміряним часом підзадач' % max_p, 150, 95)
        worst = max(1 - float(get[(p, 'block')]['speedup']) / p for p in range(2, max_p + 1))
        self.p('Стратегія block втрачає до %d %% прискорення через дисбаланс: сусідні префікси мають схожу '
               'вартість, і одному воркеру дістається «дорожчий» блок. Dynamic і cyclic тримаються біля '
               'ідеалу: при p = %d S = %s (dynamic), %s (cyclic) і %s (block). Dynamic додатково захищає від '
               'тимчасово повільних VM, але робить %d RPC-викликів замість p.'
               % (round(worst * 100), max_p, f2(float(get[(max_p, 'dynamic')]['speedup'])),
                  f2(float(get[(max_p, 'cyclic')]['speedup'])), f2(float(get[(max_p, 'block')]['speedup'])),
                  len(secs)))

    def sec_gcp(self, gcp):
        self.h('10 РЕЗУЛЬТАТИ В GOOGLE CLOUD')
        self.p('Конфігурація: Google Compute Engine, зона %s, Container-Optimized OS, образ %s; master і '
               'воркери – %s (1 vCPU, 3,75 ГБ); N = %d, 3 запуски на конфігурацію.'
               % (code('europe-north1-a'), code('hummer12007/parcs-node'), code('n1-standard-1'), N))
        header = ['Версія', 'p', 'T, с (медіана)', 'S', 'E', 'D']
        widths = [32, 14, 36, 26, 26, 31]
        if not gcp or not gcp['table']:
            rows = [['послідовна', '–', '', '1,00', '–', '–']]
            rows += [['dynamic', p, '', '', '', ''] for p in (1, 2, 3, 4)]
            rows += [['cyclic', 4, '', '', '', ''], ['block', 4, '', '', '', '']]
            self.table('Час і прискорення в Google Cloud, N = %d' % N, header, rows, widths,
                       note='Таблиця заповнюється автоматично: після запуску bench/bench.py у Google Cloud '
                            'виконайте python3 docs/build_report.py (додаток А).')
            return
        tab = gcp['table']
        rows = [['послідовна', '–', f2(gcp['t_seq']) if gcp['t_seq'] else '', '1,00', '–', '–']]
        for key in sorted(tab, key=lambda k: (k[0] != 'dynamic', k[0] == 'block', k[1])):
            r = tab[key]
            rows.append([key[0], key[1], f2(r['time']), f2(r['speedup']) if r['speedup'] else '',
                         f2(r['eff']) if r['eff'] else '', f2(r['imb'], 3) if r['imb'] else '–'])
        self.p('Усі %d %s %s. Результати – у табл. 4 і на рис. 4–5.'
               % (gcp['runs'], runs_word(gcp['runs']), 'повернули правильну кількість розв\'язків' if gcp['all_correct']
                  else 'завершилися, але не всі відповіді збіглися з OEIS – див. results/gcp_n15.csv'))
        self.table('Час і прискорення в Google Cloud (n1-standard-1), N = %d' % N, header, rows, widths)
        prefix = os.path.join(ROOT, 'results', 'gcp_n%d' % N)
        if not os.path.exists(prefix + '_speedup.png'):
            import plot_results
            rows_csv = plot_results.load([prefix + '.csv'])
            t_seq, _, table = plot_results.summarize(rows_csv, N)
            plot_results.plot(table, t_seq, N, 'GCP, n1-standard-1', prefix)
        self.figure(prefix + '_time.png', 'Час виконання в Google Cloud, N = %d' % N, 150, 95)
        self.figure(prefix + '_speedup.png', 'Прискорення в Google Cloud, N = %d' % N, 150, 95)
        best = max((k for k in tab if k[0] == 'dynamic'), key=lambda k: k[1], default=None)
        if best and tab[best]['speedup']:
            r = tab[best]
            self.p('На %d воркерах (окремі VM) прискорення становить %s, ефективність – %s, дисбаланс – %s.'
                   % (best[1], f2(r['speedup']), f2(r['eff']), f2(r['imb'], 3) if r['imb'] else '–'))

    def sec_conclusions(self, local, sim, gcp):
        self.h('ВИСНОВКИ', centered=True)
        d2 = local['table'].get(('dynamic', 2))
        d1 = local['table'].get(('dynamic', 1))
        get = {(int(r['p']), r['strategy']): r for r in sim}
        max_p = max((p for p, _ in get), default=8)
        items = [
            "Реалізовано послідовний і паралельний алгоритми підрахунку розв'язків задачі про N ферзів на "
            "бітових масках; результати для N = 1…16 збігаються з OEIS A000170.",
            'Декомпозиція на %s незалежних підзадач не потребує обміну даними між воркерами, тому задача '
            'добре масштабується в ПАРКС-Python.' % ('97' if N == 15 else 'незалежні'),
        ]
        if d1 and d2:
            items.append('Накладні витрати ПАРКС при одному воркері – близько %d %%; при двох воркерах на двох '
                         'ядрах прискорення сягає %s.'
                         % (round((d1['time'] / local['t_seq'] - 1) * 100), f2(d2['speedup'])))
        items.append('Воркери, які ділять ядра, не дають виграшу, тому в хмарі кожен воркер розміщується на '
                     'окремій VM з 1 vCPU.')
        if (max_p, 'block') in get:
            items.append('Стратегія розподілу важлива вже для 4–8 воркерів: за моделлю при p = %d block дає '
                         'S = %s, cyclic – %s, dynamic – %s.'
                         % (max_p, f2(float(get[(max_p, 'block')]['speedup'])),
                            f2(float(get[(max_p, 'cyclic')]['speedup'])),
                            f2(float(get[(max_p, 'dynamic')]['speedup']))))
        items.append('Розгортання з методичних рекомендацій (create-with-container) після 31.07.2026 не '
                     'працює; контейнер ПАРКС запускається на Container-Optimized OS через startup-script без '
                     'змін у самому ПАРКС.')
        if gcp and gcp['table']:
            best = max((k for k in gcp['table'] if k[0] == 'dynamic'), key=lambda k: k[1], default=None)
            if best and gcp['table'][best]['speedup']:
                r = gcp['table'][best]
                items.append('У Google Cloud на %d воркерах отримано прискорення %s при ефективності %s.'
                             % (best[1], f2(r['speedup']), f2(r['eff'])))
        self.bullets(items, numbered=True)
        self.p('Код проєкту: %s.' % esc(self.a.github), 'body')

    def sec_sources(self):
        self.h('СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ', centered=True)
        refs = [
            "Дерев'янченко О. В. ПАРКС-JAVA система для паралельних обчислень на комп'ютерних мережах: "
            "навчальний посібник. – Київ, 2011. – 60 с.",
            "Anisimov A., Derevianchenko O., Kuliabko P., Fedorus O. PARCS Technology: Concept and "
            "Implementations // Cybernetics and Systems Analysis. – 2023. – Vol. 59. – P. 166–179.",
            "Anisimov A., Derevianchenko O., Kuliabko P., Fedorus O. Programming System PARCS // Journal of "
            "Computer and Communications. – 2017. – Vol. 5, No. 9. – P. 129–139.",
            "Дерев'янченко О. В., Сакевич Р. Д. Застосування системи ПАРКС-Java та Google Cloud Platform для "
            "хмарних обчислень // Вісник КНУ імені Тараса Шевченка. Сер. ФМН. – 2017. – № 4. – С. 69–74.",
            'PARCS-Python: Google Cloud. Методичні рекомендації. – КНУ, 2025. – URL: '
            'https://mi.csc.knu.ua/wp-content/uploads/2025/09/PARCS-Python_Google_Cloud_0925.pdf',
            'PARCS-Python [Електронний ресурс]. – URL: https://github.com/Hummer12007/parcs-python',
            'Compute Engine container startup agent deprecation [Електронний ресурс] // Google Cloud '
            'Documentation. – URL: https://docs.cloud.google.com/compute/docs/deprecations/'
            'container-startup-agent-on-compute',
            'Migrate containers that are deployed on VMs during VM creation [Електронний ресурс] // Google '
            'Cloud Documentation. – URL: https://docs.cloud.google.com/compute/docs/containers/migrate-containers',
            'Supplemental Terms and Conditions for Google Cloud Platform Free Trial [Електронний ресурс]. – '
            'URL: https://cloud.google.com/terms/trial',
            'A000170: Number of ways of placing n nonattacking queens on an n X n board [Електронний ресурс] '
            '// OEIS. – URL: https://oeis.org/A000170',
        ]
        for i, r in enumerate(refs, 1):
            self.story.append(Paragraph(esc(r), self.s['bullet_l'], bulletText='%d.' % i))

    def app_guide(self):
        self.story.append(PageBreak())
        self.h('ДОДАТОК А<br/>Інструкція із запуску', centered=True,
               toc_text='ДОДАТОК А. Інструкція із запуску')
        steps = [
            ('А.1 Підготовка',
             ['Google-акаунт з активованим Google Cloud (пробний період, потрібна банківська картка) і '
              'акаунт GitHub.',
              'Створіть на github.com публічний репозиторій %s і завантажте в нього вміст архіву '
              '(Add file → Upload files, перетягнути всі папки).' % code('parcs-nqueens'),
              'У консолі console.cloud.google.com створіть проєкт і відкрийте Cloud Shell (кнопка «>_» '
              'угорі праворуч).']),
        ]
        for title, items in steps:
            self.p('<b>%s</b>' % title, 'body')
            self.bullets(items, numbered=True, style='bullet_l')
        self.p('<b>А.2 Розгортання ПАРКС (Cloud Shell)</b>', 'body')
        self.code_block('''git clone https://github.com/<login>/parcs-nqueens.git
cd parcs-nqueens
gcloud config set project <PROJECT_ID>
bash deploy/gcp/deploy.sh 4          # master + 4 воркери, 3-5 хв''')
        self.p('Скрипт закінчується рядком «registered workers: 4/4» і адресою веб-інтерфейсу '
               '%s. Для перевірки в браузері: Add Job → solution %s, input %s → на сторінці Jobs '
               'має з\'явитися результат «Solutions = 73712 … OK».'
               % (code('http://<EXTERNAL_IP>:8080'), code('src/nqueens_parallel.py'), code('input/n13.txt')))
        self.p('<b>А.3 Тестування (≈10 хв)</b>', 'body')
        self.code_block('''python3 bench/bench.py --master http://<EXTERNAL_IP>:8080 --n 15 \\
    --workers 1,2,3,4 --repeats 3 --sequential --out results/gcp_n15.csv
python3 bench/bench.py --master http://<EXTERNAL_IP>:8080 --n 15 \\
    --workers 4 --repeats 3 --strategies block,cyclic --out results/gcp_n15.csv''')
        self.p('<b>А.4 Звіт із хмарними результатами</b>', 'body')
        self.code_block('''pip install --user reportlab matplotlib
python3 bench/plot_results.py results/gcp_n15.csv --label "GCP, n1-standard-1"
python3 docs/build_report.py --github https://github.com/<login>/parcs-nqueens
cloudshell download report/Lab1_PARCS_NQueens.pdf''')
        self.p('<b>А.5 Видалення ресурсів</b> (обов\'язково, щоб VM не витрачали кредити):', 'body')
        self.code_block('''bash deploy/gcp/destroy.sh 4
gcloud compute instances list        # має бути порожньо''')
        self.p('<b>А.6 Якщо щось пішло не так</b>', 'body')
        self.bullets([
            'Воркери не реєструються понад 5 хв: %s; журнал startup-script – %s.'
            % (code('gcloud compute ssh parcs-worker-1 --zone europe-north1-a --command "sudo docker ps -a; sudo docker logs parcs"'),
               code('sudo journalctl -u google-startup-scripts.service')),
            'Помилка квоти CPUS або IN_USE_ADDRESSES: менше воркерів (%s) або інша зона (%s).'
            % (code('bash deploy/gcp/deploy.sh 3'), code('ZONE=europe-west1-b bash deploy/gcp/deploy.sh 4')),
            'Тип n1-standard-1 недоступний у зоні: %s (2 vCPU на VM, тому master + 3 воркери в межах 8 vCPU).'
            % code('MACHINE=e2-standard-2 bash deploy/gcp/deploy.sh 3'),
            'Повторне розгортання після невдалої спроби: спочатку %s.' % code('bash deploy/gcp/destroy.sh 8'),
        ], style='bullet_l')

    def app_listings(self):
        self.story.append(PageBreak())
        self.h('ДОДАТОК Б<br/>Лістинги програм', centered=True, toc_text='ДОДАТОК Б. Лістинги програм')
        for rel in ('src/nqueens_parallel.py', 'src/nqueens_sequential.py', 'deploy/gcp/startup.sh'):
            with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
                text = f.read()
            self.p('<b>Лістинг: %s</b>' % esc(rel), 'body_ni')
            self.story.append(Spacer(1, 4))
            self.story.append(Preformatted(text.rstrip('\n'), self.s['listing'], maxLineLength=92))
            self.story.append(Spacer(1, 12))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--student', default=STUDENT)
    ap.add_argument('--group', default=GROUP)
    ap.add_argument('--teacher', default=TEACHER)
    ap.add_argument('--github', default=GITHUB)
    ap.add_argument('--output', default='Lab1_PARCS_NQueens.pdf')
    args = ap.parse_args()
    register_fonts()
    out = Builder(args).build()
    print('Saved %s' % out)


if __name__ == '__main__':
    main()
