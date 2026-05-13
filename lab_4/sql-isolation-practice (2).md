# ПРАКТИКА: АНОМАЛИИ ИЗОЛЯЦИИ В SQL

## ЦЕЛЬ

Показать на практике, что при параллельной работе с БД могут возникать аномалии изоляции.

Нужно воспроизвести несколько примеров из списка:

- `dirty read`;
- `non-repeatable read`;
- `phantom read`;
- `lost update`.

## ФОРМАТ

Нужно взять любую SQL-базу данных и подготовить простой сценарий с параллельными транзакциями.

## ЧТО НУЖНО СДЕЛАТЬ

Для каждой выбранной аномалии нужно:

- подготовить таблицу и тестовые данные;
- описать две параллельные транзакции;
- показать шаги воспроизведения;
- зафиксировать результат.

## ЧТО СДАТЬ

- SQL-скрипты для создания таблиц и тестовых данных;
- Отчет.

## ЧТО ДОЛЖНО БЫТЬ В ОТЧЕТЕ

- какие аномалии были выбраны;
- шаги воспроизведения;
- полученный результат (скриншоты логов и таблиц в БД);
- как ее можно избежать.

## ОЦЕНИВАНИЕ (10 БАЛЛОВ)

- `8 баллов` — по 2 балла за кажду описанную анамалию;

- `1 балл` — описание, как можно избежать аномалии;
- `1 балл` — отчет оформлен понятно и есть все скриншоты.

---








# ОТЧЕТ

## Выбранные аномалии

- dirty read
- non-repeatable read
- phantom read
- lost update

## СУБД и настройки

СУБД: Microsoft SQL Server (T-SQL).

Параллельность: открыть 2 окна запросов (Session A и Session B) в SSMS/Azure Data Studio и выполнять шаги по очереди.

## SQL-скрипт: создание таблиц и тестовых данных

Выполнить один раз:

```sql
IF OBJECT_ID(N'dbo.accounts', N'U') IS NOT NULL
  DROP TABLE dbo.accounts;

CREATE TABLE dbo.accounts (
  id INT NOT NULL CONSTRAINT pk_accounts PRIMARY KEY,
  owner_name NVARCHAR(100) NOT NULL,
  balance INT NOT NULL
);

INSERT INTO dbo.accounts (id, owner_name, balance)
VALUES (1, N'Alice', 100), (2, N'Bob', 100);
```

Чтобы быстро вернуть данные в исходное состояние между экспериментами:

```sql
UPDATE dbo.accounts
SET balance = CASE id WHEN 1 THEN 100 WHEN 2 THEN 100 END
WHERE id IN (1, 2);
```

---

## 1) Dirty read

### Шаги воспроизведения

Session A:

```sql
BEGIN TRAN;

UPDATE dbo.accounts
SET balance = 999
WHERE id = 1;
```

Session B:

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
BEGIN TRAN;

SELECT id, owner_name, balance
FROM dbo.accounts
WHERE id = 1;

COMMIT;
```

Session A:

```sql
ROLLBACK;

SELECT id, owner_name, balance
FROM dbo.accounts
WHERE id = 1;
```

### Результат

- Session B увидит `balance = 999`, хотя транзакция Session A не была зафиксирована.
- После `ROLLBACK` в Session A значение снова станет `100`, то есть Session B прочитал данные, которых “никогда не существовало” в зафиксированном состоянии.

### Как избежать

- Не использовать `READ UNCOMMITTED` и `NOLOCK` для бизнес-данных.
- Использовать как минимум `READ COMMITTED` (или выше).

---

## 2) Non-repeatable read

### Шаги воспроизведения

Session A:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRAN;

SELECT id, owner_name, balance
FROM dbo.accounts
WHERE id = 1;
```

Session B:

```sql
BEGIN TRAN;

UPDATE dbo.accounts
SET balance = 200
WHERE id = 1;

COMMIT;
```

Session A (повторное чтение в рамках той же транзакции):

```sql
SELECT id, owner_name, balance
FROM dbo.accounts
WHERE id = 1;

COMMIT;
```

### Результат

- В Session A первый `SELECT` вернет `balance = 100`, а второй — `balance = 200`.
- Это и есть non-repeatable read: повторное чтение одной и той же строки дает разные результаты из‑за параллельного `UPDATE`.

### Как избежать

- Поднять уровень изоляции до `REPEATABLE READ` или `SERIALIZABLE`.
- Либо использовать блокировки чтения на уровне запроса (например, `WITH (HOLDLOCK)`), когда важно “заморозить” читаемые строки до конца транзакции.

---

## 3) Phantom read

Для воспроизведения нужна таблица с несколькими строками и запрос с предикатом.

Подготовка (выполнить один раз):

```sql
IF OBJECT_ID(N'dbo.orders', N'U') IS NOT NULL
  DROP TABLE dbo.orders;

CREATE TABLE dbo.orders (
  id INT IDENTITY(1, 1) NOT NULL CONSTRAINT pk_orders PRIMARY KEY,
  account_id INT NOT NULL,
  amount INT NOT NULL
);

INSERT INTO dbo.orders (account_id, amount)
VALUES (1, 50), (1, 150), (1, 250);
```

### Шаги воспроизведения

Session A:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRAN;

SELECT COUNT(*) AS big_orders
FROM dbo.orders
WHERE account_id = 1 AND amount >= 200;
```

Session B:

```sql
BEGIN TRAN;

INSERT INTO dbo.orders (account_id, amount)
VALUES (1, 300);

COMMIT;
```

Session A (повтор того же запроса):

```sql
SELECT COUNT(*) AS big_orders
FROM dbo.orders
WHERE account_id = 1 AND amount >= 200;

COMMIT;
```

### Результат

- Первый `COUNT(*)` в Session A вернет `1` (только `250`).
- После вставки Session B второй `COUNT(*)` в Session A вернет `2` (добавится “фантом” `300`).

### Как избежать

- Использовать `SERIALIZABLE` для транзакций, которым нужна защита от фантомов.
- Или проектировать операции так, чтобы не зависеть от “множества строк по предикату” (например, фиксировать выбранный набор ключей заранее).

---

## 4) Lost update

Идея: обе сессии читают одно и то же значение, считают новое локально и затем записывают его, из‑за чего одна запись “перетирает” другую.

Перед началом вернуть `accounts` к исходным значениям:

```sql
UPDATE dbo.accounts SET balance = 100 WHERE id = 1;
```

### Шаги воспроизведения

Session A:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRAN;

DECLARE @balanceA INT;
SELECT @balanceA = balance
FROM dbo.accounts
WHERE id = 1;

WAITFOR DELAY '00:00:05';

UPDATE dbo.accounts
SET balance = @balanceA + 10
WHERE id = 1;

COMMIT;
```

Session B (запустить сразу после первого `SELECT` в Session A, пока Session A ждет):

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRAN;

DECLARE @balanceB INT;
SELECT @balanceB = balance
FROM dbo.accounts
WHERE id = 1;

UPDATE dbo.accounts
SET balance = @balanceB - 20
WHERE id = 1;

COMMIT;
```

Проверка:

```sql
SELECT id, owner_name, balance
FROM dbo.accounts
WHERE id = 1;
```

### Результат

- Ожидаемый “правильный” итог: `100 + 10 - 20 = 90`.
- Возможный фактический итог: `80` или `110` (в зависимости от порядка фиксации), потому что каждая транзакция обновляет строку на основании устаревшего прочитанного значения.

### Как избежать

- Делать “атомарный” `UPDATE` без чтения в переменную: `UPDATE ... SET balance = balance + 10`.
- Использовать блокировки на чтение для сценария read-modify-write (например, `SELECT ... WITH (UPDLOCK, HOLDLOCK)`).
- Использовать оптимистическую конкуренцию: поле версии (rowversion) и проверку `WHERE id = 1 AND row_ver = @oldRowVer`.

---

## Что приложить как скриншоты

- Окна Session A и Session B со всеми шагами для каждой аномалии.
- Результаты `SELECT`/`COUNT(*)` (до и после) и итоговое состояние таблиц.
