# Задача про N ферзів у системі ПАРКС (PARCS-Python) на Google Cloud

Лабораторна робота з курсу «Хмарні обчислення» (КНУ ім. Тараса Шевченка, ФКНК), завдання 1.

**Тема:** паралельний підрахунок кількості розв'язків задачі про N ферзів
(перебір з поверненням на бітових масках, Python).
**Платформа:** [PARCS-Python](https://github.com/Hummer12007/parcs-python), образ `hummer12007/parcs-node`.
**Хмара:** Google Compute Engine (Container-Optimized OS + Docker).

## Структура

```
src/nqueens_parallel.py     паралельний розв'язувач ПАРКС (map на воркерах, reduce на master)
src/nqueens_sequential.py   послідовна версія (як задача ПАРКС або як звичайний скрипт)
input/                      вхідні файли (n=13..16, стратегії розподілу)
deploy/gcp/                 розгортання в GCP: deploy.sh, destroy.sh, startup.sh
bench/bench.py              автоматичне тестування через REST API master (лише stdlib)
bench/plot_results.py       таблиця прискорення/ефективності + графіки
bench/simulate_balance.py   модель балансування навантаження block / cyclic / dynamic
local/parcs_local.py        локальний стенд із тим самим API, що й ПАРКС (налагодження без хмари)
results/                    CSV, таблиці та графіки
docs/                       генератор PDF-звіту (build_report.py) і схема архітектури
report/                     готовий PDF-звіт
```

## Алгоритм

* **Послідовний:** бектрекінг по рядках; зайняті стовпці й діагоналі зберігаються в трьох
  бітових масках, вільні клітинки рядка - `full & ~(cols | ld | rd)`. Використовується дзеркальна
  симетрія першого рядка: рахуємо лише ліву половину стовпців і множимо на 2.
* **Паралельний:** master фіксує ферзів у перших `depth` рядках (за замовчуванням 2) і отримує
  набір незалежних підзадач (для N = 15 - 97 підзадач). Підзадачі розподіляються між воркерами:
  * `block` - суцільними блоками;
  * `cyclic` - по колу (round-robin);
  * `dynamic` - «мішок задач»: наступну підзадачу отримує воркер, що звільнився першим.
  Воркер (`mymap`) повертає кількість розв'язків і свій час роботи; master (`myreduce`) підсумовує.
* Результат перевіряється за OEIS A000170 (N = 14 → 365 596, N = 15 → 2 279 184, N = 16 → 14 772 512).

Формат вхідного файлу:

```
n=15
depth=2
strategy=dynamic   # block | cyclic | dynamic
chunk=1            # розмір порції для dynamic
```

## Розгортання в Google Cloud

> Методичка використовує `gcloud compute instances create-with-container`. Google вимкнув цей
> механізм (container startup agent) **31.07.2026**, тому тут VM створюються з образу
> Container-Optimized OS, а контейнер ПАРКС запускає startup-script (`docker run --network host`).

Найпростіше - у [Google Cloud Shell](https://shell.cloud.google.com) (gcloud уже встановлений):

```bash
git clone https://github.com/<your-login>/parcs-nqueens.git
cd parcs-nqueens
gcloud config set project <PROJECT_ID>
bash deploy/gcp/deploy.sh 4       # master + 4 воркери (n1-standard-1, europe-north1-a)
```

Скрипт створює правила брандмауера (`parcs-allow-internal` - трафік між вузлами,
`parcs-allow-ui` - порт 8080), master, воркери й чекає, поки воркери зареєструються.
Веб-інтерфейс: `http://<EXTERNAL_IP master>:8080`.

У безкоштовному пробному періоді одночасно доступно не більше 8 vCPU, тобто з
`n1-standard-1` - master + до 7 воркерів.

### Запуск вручну (веб-інтерфейс)

*Add Job* → solution: `src/nqueens_parallel.py`, input: `input/n15.txt`.
Послідовна версія: solution `src/nqueens_sequential.py` (рахує на master).
Зареєстровані воркери: `http://<EXTERNAL_IP>:8080/api/worker`. Щоб запустити задачу на меншій
кількості воркерів, зайві вимикаються через API (так само робить `bench.py`):

```bash
curl -X POST http://<EXTERNAL_IP>:8080/api/worker/3/disable   # і /enable, щоб повернути
```

### Автоматичне тестування

```bash
python3 bench/bench.py --master http://<EXTERNAL_IP>:8080 --n 15 \
    --workers 1,2,3,4 --repeats 3 --sequential --out results/gcp_n15.csv
python3 bench/bench.py --master http://<EXTERNAL_IP>:8080 --n 15 \
    --workers 4 --repeats 3 --strategies block,cyclic --out results/gcp_n15.csv
pip install matplotlib
python3 bench/plot_results.py results/gcp_n15.csv --label "GCP, n1-standard-1"
```

`bench.py` для кожного p вмикає рівно p воркерів, надсилає задачу через `/api/job`,
чекає на `/api/job/<id>/output` і записує рядок `RESULT_JSON` у CSV.

### Видалення ресурсів

```bash
bash deploy/gcp/destroy.sh 4
```

## Звіт (PDF)

```bash
pip install --user reportlab matplotlib
python3 docs/build_report.py --github https://github.com/<your-login>/parcs-nqueens
# -> report/Lab1_PARCS_NQueens.pdf; якщо є results/gcp_n15.csv, розділ 10 заповнюється сам
```

Покрокова інструкція запуску - у додатку А звіту.

## Локальне налагодження без хмари

```bash
pip install Pyro4 flask matplotlib
python local/parcs_local.py run --solution src/nqueens_parallel.py --input input/n13.txt --workers 2
python local/parcs_local.py serve --workers 4     # той самий REST API, що й master ПАРКС
python bench/bench.py --master http://127.0.0.1:8080 --n 14 --workers 1,2
python src/nqueens_sequential.py input/n14.txt
```

`parcs_local.py` відтворює механіку ПАРКС: на кожному «воркері» модуль розв'язку
реєструється в `Pyro4.Daemon`, а master викликає `Solver(workers, input, output).solve()`
з асинхронними Pyro4-проксі.

## Результати

* `results/local_n15_*` - перевірка на локальному стенді (2 ядра).
* `results/simulation_n15*` - модель балансування за виміряним часом 97 підзадач.
* `results/gcp_n15_*` - заміри в Google Cloud (з'являються після запуску `bench.py`).
