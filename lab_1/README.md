# Транзакции Интернет-Магазина

Этот проект реализует SQL-транзакции для интернет-магазина с использованием Python и SQLAlchemy.

## Таблицы

- Customers (CustomerID, FirstName, LastName, Email)
- Products (ProductID, ProductName, Price)
- Orders (OrderID, CustomerID, OrderDate, TotalAmount)
- OrderItems (OrderItemID, OrderID, ProductID, Quantity, Subtotal)

## Сценарии

1. **Размещение заказа**: Создает новый заказ, добавляет позиции заказа и обновляет общую сумму.
2. **Обновление email клиента**: Атомарно обновляет адрес электронной почты клиента.
3. **Добавление продукта**: Атомарно добавляет новый продукт.

## Запуск проекта

1. Соберите и запустите с помощью Docker Compose:
   ```bash
   docker-compose up --build
   ```

Это запустит PostgreSQL и выполнит Python-скрипт, демонстрирующий транзакции.