# ПРАКТИКА: СРАВНЕНИЕ ТИПОВ КЕШИРОВАНИЯ

## ЦЕЛЬ

Сделать три простых примера одной и той же системы с разными типами кеширования и сравнить их в одинаковых условиях:

- `Lazy Loading` / `Cache-Aside` / `Write-Around`;
- `Write-Through`;
- `Write-Back`.

## ФОРМАТ

Одна и та же система должна быть реализована в трех вариантах.

Минимальный состав:

- `load-generator`; (например Jmeter или самописный)
- `application`;
- `cache`; (Redis/Apache Ignit/etc...)
- `БД`.

Меняется только стратегия работы с кешем.

## ЧТО НУЖНО СДЕЛАТЬ

### 1. Lazy Loading / Cache-Aside

- чтение идет через кеш;
- если данных нет, они берутся из БД и кладутся в кеш;
- запись идет сразу в БД.

### 2. Write-Through

- чтение идет через кеш;
- запись сразу попадает и в кеш, и в БД.

### 3. Write-Back

- чтение идет через кеш;
- запись сначала попадает в кеш;
- в БД данные отправляются позже.

## ЕДИНЫЙ ТЕСТ

Для всех трех вариантов нужен один и тот же тест.

- одинаковый набор данных;
- одинаковое число запросов;
- одинаковая длительность;

Минимум нужно сделать 3 прогона:

- `read-heavy`, например `80% read / 20% write`;
- `balanced`, например `50% read / 50% write`;
- `write-heavy`, например `20% read / 80% write`.

## МЕТРИКИ

Нужно измерить:

- `throughput` (`req/sec`);
- среднюю задержку;
- количество обращений в БД;
- hit rate кеша.

Для `Write-Back` желательно отдельно показать, что происходит при накоплении записей.

## ЧТО СДАТЬ

- код;
- итоговый отчет

## ЧТО ДОЛЖНО БЫТЬ В ОТЧЕТЕ

- таблица результатов по всем трем вариантам;
- описание тестов
- выводы, какой тип кеширования лучше:
  - для чтения;
  - для записи;
  - для смешанной нагрузки;
- скрины консоли, где видно логи работы тестов

## ОЦЕНИВАНИЕ (10 БАЛЛОВ)

- `3 балла` — реализованы все 3 типа кеширования; (по баллу за тип)
- `3 балла` — сделан единый тест для всех реализованных вариантов; (по баллу за тип)
- `4 балла` — собраны и показаны все требуемые метрики; (по баллу за метрику)

Все должно быть залито на гит

---

## РЕАЛИЗАЦИЯ (КОД)

Минимальный состав реализован так:

- `application`: [server.py](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/server.py) (HTTP API)
- `cache`: [cache.py](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/cache.py) (in-memory)
- `БД`: [db.py](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/db.py) (SQLite + искусственная задержка для сравнения)
- `load-generator`: [load_generator.py](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/load_generator.py)

Стратегии кеширования:

- `Cache-Aside / Write-Around`: [CacheAsideWriteAroundStrategy](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/strategies.py#L41-L92)
- `Write-Through`: [WriteThroughStrategy](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/strategies.py#L95-L146)
- `Write-Back`: [WriteBackStrategy](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/strategies.py#L215-L250) + фоновый flush [WriteBackCoordinator](file:///c:/Users/gas99/Desktop/%D0%BC%D1%83%D1%81%D0%BE%D1%80%D0%BA%D0%B0/isp/isp/lab_3/cache_comparison/strategies.py#L149-L212)

## КАК ЗАПУСКАТЬ

Требуется только Python 3.11+ (используется только стандартная библиотека).

### 1) Прогон всех вариантов + таблица

Из папки `lab_3`:

```bash
python -m cache_comparison.run_all --keys 1000 --workers 40 --duration-s 10 --db-delay-ms 5 --out-json results.json
```

На stdout печатается markdown-таблица. В `results.json` сохраняются “сырые” данные прогона (удобно для отчета).

### 2) Ручной запуск одного варианта

Подготовить БД:

```bash
python -m cache_comparison.seed_db --db-path .\data\demo.sqlite --keys 1000 --seed 1
```

Запустить приложение:

```bash
python -m cache_comparison.server --db-path .\data\demo.sqlite --strategy cache_aside --db-delay-ms 5 --allow-shutdown
```

Запустить нагрузку:

```bash
python -m cache_comparison.load_generator --base-url http://127.0.0.1:8000 --keys 1000 --workers 40 --duration-s 10 --read-pct 80 --write-pct 20
```

## ЕДИНЫЙ ТЕСТ (ПРОФИЛИ)

Используются три профиля, одинаковые для всех стратегий:

- `read-heavy`: 80% read / 20% write
- `balanced`: 50% read / 50% write
- `write-heavy`: 20% read / 80% write

## МЕТРИКИ (КАК СЧИТАЮТСЯ)

- `throughput (req/sec)`: на стороне load-generator (`requests / wall_time`)
- `avg latency`: средняя задержка на стороне load-generator
- `DB calls`: дельта `db.reads` и `db.writes` по `/metrics` до/после прогона
- `cache hit rate`: по дельте `cache.hits`/`cache.misses` до/после прогона

Для `Write-Back` дополнительно выводится `write_back.pending_keys` во время `write-heavy` (накопление грязных записей) и `max_pending_keys` в метриках.

## РЕЗУЛЬТАТЫ (ПРИМЕР)

Пример таблицы с одного прогона (значения зависят от параметров `--workers`, `--db-delay-ms`, `--duration-s` и железа):

| strategy | profile | throughput_rps | avg_latency_ms | db_reads | db_writes | cache_hit_rate | wb_max_pending |
|---|---|---:|---:|---:|---:|---:|---:|
| cache_aside | read-heavy | 162.88 | 229.91 | 458 | 151 | 0.198 |  |
| cache_aside | balanced | 67.49 | 530.92 | 25 | 167 | 0.853 |  |
| cache_aside | write-heavy | 42.69 | 842.83 | 6 | 167 | 0.872 |  |
| write_through | read-heavy | 168.92 | 223.68 | 439 | 158 | 0.266 |  |
| write_through | balanced | 73.90 | 484.37 | 7 | 181 | 0.963 |  |
| write_through | write-heavy | 46.37 | 769.89 | 1 | 185 | 0.980 |  |
| write_back | read-heavy | 825.34 | 42.35 | 792 | 130 | 0.753 | 506 |
| write_back | balanced | 68750.80 | 0.57 | 10 | 125 | 0.994 | 883 |
| write_back | write-heavy | 1136.39 | 31.68 | 1 | 131 | 0.999 | 994 |

## ВЫВОДЫ (КРАТКО)

- Для чтения при достаточном hit rate кеша выигрывают все стратегии с кешем; cache-aside и write-through близки по чтению, отличие больше видно по записи.
- Для записи write-back обычно дает максимальный throughput и минимальную latency (запись не блокируется на БД), но накапливает грязные записи и требует фоновой синхронизации.
- Для смешанной нагрузки write-back часто быстрее остальных, но компромисс — eventual consistency и риск потери данных при падении до flush (в этой учебной реализации тоже).
