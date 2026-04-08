# Схема данных в БД (Микросервисы)

В микросервисной архитектуре каждый сервис владеет своей схемой данных для обеспечения независимости и масштабируемости.

## ER-диаграмма (Распределенная)

```mermaid
erDiagram
    %% Схема Profile Service
    subgraph Profile_DB ["Profile Service DB"]
        USER {
            bigint tg_id PK "ID из Telegram"
            string username "Никнейм"
            string full_name "Имя"
            int age "Возраст"
            string gender "Пол"
            string preference "Предпочтения"
            text bio "О себе"
            string photo_file_id "ID фото"
            timestamp created_at "Регистрация"
        }
    end

    %% Схема Interaction Service
    subgraph Interaction_DB ["Interaction Service DB"]
        INTERACTION {
            bigint user_from_id FK "Кто"
            bigint user_to_id FK "Кому"
            string type "Тип (like/dislike)"
            timestamp created_at "Когда"
        }
        
        MATCH {
            uuid id PK "ID мэтча"
            bigint user_1_id "Участник 1"
            bigint user_2_id "Участник 2"
            timestamp created_at "Когда"
        }
    end

    %% Схема Matching Service (ReadOnly Cache)
    subgraph Matching_Cache ["Matching Service Cache"]
        GEO_INDEX {
            bigint user_id PK "ID пользователя"
            point location "Координаты"
            int age "Возраст"
        }
    end

    USER ||--o{ INTERACTION : "результат"
    INTERACTION ||--o| MATCH : "создает"
```

### Разделение ответственности:
1. **Profile DB**: Хранит только персональные данные. Другие сервисы получают их по запросу или через события.
2. **Interaction DB**: Хранит историю лайков и мэтчей. Не зависит от изменений в профиле.
3. **Matching Cache**: Оптимизированное хранилище (Redis или отдельная таблица в PostgreSQL с PostGIS) для быстрого гео-поиска.
4. **Notification Queue**: (Не БД) Хранит временные сообщения в Message Broker.
