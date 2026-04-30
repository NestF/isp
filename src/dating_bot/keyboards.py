from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def kb_name_default(default_name: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=default_name)]], resize_keyboard=True)


def kb_bio_skip() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📝 Оставить пустым")]], resize_keyboard=True)


def kb_media() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить ещё"), KeyboardButton(text="✅ Готово")],
            [KeyboardButton(text="⏭️ Пропустить")],
        ],
        resize_keyboard=True,
    )


def kb_main() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Моя анкета"), KeyboardButton(text="💘 Мэтчи")],
            [KeyboardButton(text="👀 Смотреть анкеты")],
        ],
        resize_keyboard=True,
    )


def kb_profile_manage() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Изменить анкету"), KeyboardButton(text="🗑️ Удалить анкету")],
            [KeyboardButton(text="🏠 Домой")],
        ],
        resize_keyboard=True,
    )


def kb_confirm_delete() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Да, удалить"), KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def kb_viewing() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❤️ Лайк"), KeyboardButton(text="💔 Дизлайк")],
            [KeyboardButton(text="🏠 Домой")],
        ],
        resize_keyboard=True,
    )
