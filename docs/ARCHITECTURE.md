# Архитектура и схема дизайна (Микросервисы)

Проект строится на базе **микросервисной архитектуры** с использованием событийной модели (Event-Driven Architecture).

## Схема дизайна системы (High-Level Design)

```mermaid
graph TD
    User([Пользователь]) <--> |Telegram App| TG_API[Telegram Bot API]
    
    subgraph Gateway_Layer ["Gateway Layer"]
        Bot_Gateway["Bot Gateway Service (aiogram)"]
    end
    
    subgraph Event_Bus ["Message Broker"]
        NATS["NATS JetStream / RabbitMQ"]
    end
    
    subgraph Microservices ["Business Services"]
        Profile_Srv["Profile Service"]
        Matching_Srv["Matching Service"]
        Interaction_Srv["Interaction Service"]
        Notification_Srv["Notification Service"]
    end
    
    subgraph Storage ["Persistent Storage"]
        DB_Profile[(PostgreSQL: Profiles)]
        DB_Interact[(PostgreSQL: Likes)]
        Redis_FSM[(Redis: Sessions)]
    end
    
    TG_API <--> Bot_Gateway
    Bot_Gateway <--> Redis_FSM
    
    Bot_Gateway <--> NATS
    NATS <--> Profile_Srv
    NATS <--> Matching_Srv
    NATS <--> Interaction_Srv
    NATS <--> Notification_Srv
    
    Profile_Srv <--> DB_Profile
    Interaction_Srv <--> DB_Interact
```

### Основные принципы:
1. **Асинхронность**: Большинство операций (лайки, уведомления) обрабатываются через очередь сообщений.
2. **Изоляция данных**: Каждый сервис владеет своими данными (собственные базы данных или схемы).
3. **Масштабируемость**: Каждый микросервис может масштабироваться независимо в Docker/K8s.
4. **Отказоустойчивость**: Если сервис уведомлений временно недоступен, сообщение сохранится в брокере и будет доставлено позже.
