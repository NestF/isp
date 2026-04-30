from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    full_name = State()
    age = State()
    city = State()
    bio = State()
    media = State()


class Viewing(StatesGroup):
    active = State()

