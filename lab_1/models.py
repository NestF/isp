from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Customer(Base):
    __tablename__ = 'customers'
    CustomerID = Column(Integer, primary_key=True, autoincrement=True)
    FirstName = Column(String(50))
    LastName = Column(String(50))
    Email = Column(String(100), unique=True)

class Product(Base):
    __tablename__ = 'products'
    ProductID = Column(Integer, primary_key=True, autoincrement=True)
    ProductName = Column(String(100))
    Price = Column(Float)

class Order(Base):
    __tablename__ = 'orders'
    OrderID = Column(Integer, primary_key=True, autoincrement=True)
    CustomerID = Column(Integer, ForeignKey('customers.CustomerID'))
    OrderDate = Column(DateTime, default=datetime.utcnow)
    TotalAmount = Column(Float, default=0.0)
    customer = relationship('Customer')
    order_items = relationship('OrderItem', back_populates='order')

class OrderItem(Base):
    __tablename__ = 'order_items'
    OrderItemID = Column(Integer, primary_key=True, autoincrement=True)
    OrderID = Column(Integer, ForeignKey('orders.OrderID'))
    ProductID = Column(Integer, ForeignKey('products.ProductID'))
    Quantity = Column(Integer)
    Subtotal = Column(Float)
    order = relationship('Order', back_populates='order_items')
    product = relationship('Product')