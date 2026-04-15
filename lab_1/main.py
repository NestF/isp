from sqlalchemy.orm import Session
from models import Customer, Product, Order, OrderItem
from database import SessionLocal, create_tables
from datetime import datetime

def place_order(db: Session, customer_id: int, items: list[tuple[int, int]]):
    # items: список кортежей (product_id, quantity)
    # Создаем заказ
    order = Order(CustomerID=customer_id, OrderDate=datetime.utcnow(), TotalAmount=0.0)
    db.add(order)
    db.flush()  # to get OrderID

    total = 0.0
    for product_id, quantity in items:
        product = db.query(Product).filter(Product.ProductID == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        subtotal = product.Price * quantity
        order_item = OrderItem(OrderID=order.OrderID, ProductID=product_id, Quantity=quantity, Subtotal=subtotal)
        db.add(order_item)
        total += subtotal

    order.TotalAmount = total
    db.commit()

def update_customer_email(db: Session, customer_id: int, new_email: str):
    customer = db.query(Customer).filter(Customer.CustomerID == customer_id).first()
    if not customer:
        raise ValueError(f"Customer {customer_id} not found")
    customer.Email = new_email
    db.commit()

def add_product(db: Session, name: str, price: float):
    product = Product(ProductName=name, Price=price)
    db.add(product)
    db.commit()

if __name__ == "__main__":
    # Создаем таблицы в базе данных
    create_tables()
    db = SessionLocal()
    try:
        # Пример использования
        # Добавляем клиента
        customer = Customer(FirstName="John", LastName="Doe", Email="john3@example.com")
        db.add(customer)
        db.commit()

        # Добавляем продукты
        product1 = Product(ProductName="Laptop", Price=1000.0)
        product2 = Product(ProductName="Mouse", Price=50.0)
        db.add(product1)
        db.add(product2)
        db.commit()

        # Размещаем заказ
        place_order(db, customer.CustomerID, [(product1.ProductID, 1), (product2.ProductID, 2)])

        # Обновляем email
        update_customer_email(db, customer.CustomerID, "john.doe3@example.com")

        # Добавляем новый продукт
        add_product(db, "Keyboard", 75.0)

        print("Все транзакции выполнены успешно")

        # Демонстрация результатов
        print("\nКлиенты:")
        customers = db.query(Customer).all()
        for c in customers:
            print(f"ID: {c.CustomerID}, Имя: {c.FirstName} {c.LastName}, Email: {c.Email}")

        print("\nПродукты:")
        products = db.query(Product).all()
        for p in products:
            print(f"ID: {p.ProductID}, Название: {p.ProductName}, Цена: {p.Price}")

        print("\nЗаказы:")
        orders = db.query(Order).all()
        for o in orders:
            print(f"ID: {o.OrderID}, Клиент: {o.CustomerID}, Дата: {o.OrderDate}, Сумма: {o.TotalAmount}")

        print("\nПозиции заказов:")
        order_items = db.query(OrderItem).all()
        for oi in order_items:
            print(f"ID: {oi.OrderItemID}, Заказ: {oi.OrderID}, Продукт: {oi.ProductID}, Количество: {oi.Quantity}, Сумма: {oi.Subtotal}")

    finally:
        db.close()