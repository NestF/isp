from __future__ import annotations

import logging
from typing import Iterable, Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InputMediaPhoto, InputMediaVideo, Message

from dating_bot.cache import ProfileCache
from dating_bot.config import Config
from dating_bot.fsm import Onboarding, Viewing
from dating_bot.keyboards import (
    kb_bio_skip,
    kb_confirm_delete,
    kb_main,
    kb_media,
    kb_name_default,
    kb_profile_manage,
    kb_viewing,
)
from dating_bot.matching import build_candidate_batch
from dating_bot.models import UserProfile
from dating_bot.rating import vote_dislike, vote_like
from dating_bot.repository import (
    add_referral,
    delete_profile,
    get_matches,
    get_profile,
    get_rank_info,
    has_vote,
    upsert_profile,
)
from dating_bot.ranking import compute_behavior_score, compute_combined_score, compute_primary_score
from dating_bot.text import format_profile_text

router = Router()
log = logging.getLogger(__name__)


async def safe_delete(message: Message, message_id: Optional[int]) -> None:
    if not message_id:
        return
    try:
        await message.bot.delete_message(chat_id=message.chat.id, message_id=message_id)
    except Exception:
        return


async def safe_delete_many(message: Message, message_ids: Optional[Iterable[int]]) -> None:
    if not message_ids:
        return
    for mid in message_ids:
        await safe_delete(message, int(mid))


async def cleanup_pair(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await safe_delete(message, data.get("last_bot_message_id"))
    try:
        await message.delete()
    except Exception:
        pass


async def cleanup_all(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await safe_delete(message, data.get("last_bot_message_id"))
    await safe_delete_many(message, data.get("last_card_message_ids"))
    await safe_delete(message, data.get("last_card_message_id"))
    await safe_delete(message, data.get("last_menu_message_id"))
    try:
        await message.delete()
    except Exception:
        pass


async def ask(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    await cleanup_pair(message, state)
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(last_bot_message_id=sent.message_id)


async def _send_profile_one_message(message: Message, profile: dict, reply_markup=None, include_contact: bool = False):
    caption = format_profile_text(profile)
    if include_contact:
        username = profile.get("username")
        tg_id = int(profile.get("tg_id") or 0)
        contact = f"@{username}" if username else f"tg://user?id={tg_id}"
        caption = f"{caption}\n\n📩 Контакт: {contact}"

    media = profile.get("media") or []
    if not media:
        return await message.answer(caption, reply_markup=reply_markup)

    if len(media) == 1:
        first = media[0]
        t = first.get("type")
        fid = first.get("file_id")
        try:
            if t == "photo" and fid:
                return await message.answer_photo(photo=fid, caption=caption, reply_markup=reply_markup)
            if t == "video" and fid:
                return await message.answer_video(video=fid, caption=caption, reply_markup=reply_markup)
        except Exception:
            log.exception("Не удалось отправить медиа, шлю текст")
        return await message.answer(caption, reply_markup=reply_markup)

    items = []
    for idx, m in enumerate(media[:3]):
        t = m.get("type")
        fid = m.get("file_id")
        if not t or not fid:
            continue
        item_caption = caption if idx == 0 else None
        if t == "photo":
            im = InputMediaPhoto(media=fid, caption=item_caption)
        else:
            im = InputMediaVideo(media=fid, caption=item_caption)
        items.append(im)

    if not items:
        return await message.answer(caption, reply_markup=reply_markup)

    sent_messages: list[Message] = []
    try:
        sent_messages.extend(await message.answer_media_group(media=items))
    except Exception:
        log.exception("Не удалось отправить медиа-группу, шлю текст")
        return await message.answer(caption, reply_markup=reply_markup)

    if reply_markup:
        sent_messages.append(await message.answer("Действия:", reply_markup=reply_markup))

    return sent_messages


async def _send_profile_one_message_to_chat(bot, chat_id: int, profile: dict, include_contact: bool = False):
    caption = format_profile_text(profile)
    if include_contact:
        username = profile.get("username")
        tg_id = int(profile.get("tg_id") or 0)
        contact = f"@{username}" if username else f"tg://user?id={tg_id}"
        caption = f"{caption}\n\n📩 Контакт: {contact}"

    media = profile.get("media") or []
    if not media:
        return await bot.send_message(chat_id=chat_id, text=caption)

    if len(media) == 1:
        first = media[0]
        t = first.get("type")
        fid = first.get("file_id")
        try:
            if t == "photo" and fid:
                return await bot.send_photo(chat_id=chat_id, photo=fid, caption=caption)
            if t == "video" and fid:
                return await bot.send_video(chat_id=chat_id, video=fid, caption=caption)
        except Exception:
            log.exception("Не удалось отправить медиа в чат, шлю текст")
        return await bot.send_message(chat_id=chat_id, text=caption)

    items = []
    for idx, m in enumerate(media[:3]):
        t = m.get("type")
        fid = m.get("file_id")
        if not t or not fid:
            continue
        item_caption = caption if idx == 0 else None
        if t == "photo":
            im = InputMediaPhoto(media=fid, caption=item_caption)
        else:
            im = InputMediaVideo(media=fid, caption=item_caption)
        items.append(im)

    if not items:
        return await bot.send_message(chat_id=chat_id, text=caption)

    try:
        return await bot.send_media_group(chat_id=chat_id, media=items)
    except Exception:
        log.exception("Не удалось отправить медиа-группу в чат, шлю текст")
        return await bot.send_message(chat_id=chat_id, text=caption)


async def show_card(message: Message, state: FSMContext, profile: dict, reply_markup=None) -> None:
    data = await state.get_data()
    await safe_delete_many(message, data.get("last_card_message_ids"))
    await safe_delete(message, data.get("last_card_message_id"))
    sent = await _send_profile_one_message(message, profile, reply_markup=reply_markup)
    if isinstance(sent, list):
        await state.update_data(last_card_message_ids=[m.message_id for m in sent], last_card_message_id=None)
    else:
        await state.update_data(last_card_message_id=sent.message_id, last_card_message_ids=None)


async def send_menu(message: Message, state: FSMContext) -> None:
    await cleanup_all(message, state)
    sent = await message.answer("Меню", reply_markup=kb_main())
    await state.update_data(
        last_menu_message_id=sent.message_id,
        last_card_message_id=None,
        last_card_message_ids=None,
        last_bot_message_id=None,
    )


async def _pick_next_for_viewer(
    session,
    cfg: Config,
    viewer: UserProfile,
    cache: ProfileCache | None,
) -> Optional[UserProfile]:
    viewer_id = int(viewer.tg_id)

    if cache:
        for _ in range(50):
            next_id = await cache.pop_next(viewer_id)
            if not next_id:
                break
            nid = int(next_id)
            if nid == viewer_id:
                continue
            if await has_vote(session, viewer_id, nid):
                continue
            cand = await get_profile(session, nid)
            if cand:
                return cand

    ids = await build_candidate_batch(session, cfg, viewer, limit=10)
    if not ids:
        if cache:
            await cache.clear_queue(viewer_id)
        return None

    fresh_ids: list[int] = []
    for cid in ids:
        if int(cid) == viewer_id:
            continue
        fresh_ids.append(int(cid))

    if not fresh_ids:
        if cache:
            await cache.clear_queue(viewer_id)
        return None

    head = fresh_ids[0]
    tail = fresh_ids[1:]
    if cache:
        await cache.replace_queue(viewer_id, tail)
    return await get_profile(session, head)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session_factory, cfg: Config, cache: ProfileCache | None):
    referred_by = None
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) == 2:
            arg = parts[1].strip()
            if arg.isdigit():
                referred_by = int(arg)
                if referred_by == message.from_user.id:
                    referred_by = None
    except Exception:
        referred_by = None

    async with session_factory() as session:
        profile = await get_profile(session, message.from_user.id)

    if profile:
        if cache:
            await cache.set_profile(message.from_user.id, _profile_to_dict(profile))
        await send_menu(message, state)
        return
    if cache:
        await cache.del_profile(message.from_user.id)
        await cache.del_candidate(message.from_user.id)

    await state.clear()
    await state.set_state(Onboarding.full_name)
    await state.update_data(media=[], referred_by=referred_by)
    if referred_by:
        async with session_factory() as session:
            ref_profile = await get_profile(session, referred_by)
            if ref_profile:
                await add_referral(session, cfg, referred_by)
                await session.commit()
        if cache:
            await cache.del_profile(referred_by)
    default_name = message.from_user.full_name or "Имя"
    await ask(message, state, "Как тебя зовут?", reply_markup=kb_name_default(default_name))


@router.message(Onboarding.full_name)
async def onboarding_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await ask(message, state, "Напиши имя текстом.")
        return
    await state.update_data(full_name=name)
    await state.set_state(Onboarding.age)
    await ask(message, state, "Сколько тебе лет?")


@router.message(Onboarding.age)
async def onboarding_age(message: Message, state: FSMContext):
    txt = (message.text or "").strip()
    try:
        age = int(txt)
    except ValueError:
        await ask(message, state, "Возраст должен быть числом.")
        return
    if age < 18:
        await ask(message, state, "Возраст должен быть не менее 18.")
        return
    if age > 100:
        await ask(message, state, "Возраст должен быть не более 100.")
        return
    await state.update_data(age=age)
    await state.set_state(Onboarding.city)
    await ask(message, state, "Из какого ты города?")


@router.message(Onboarding.city)
async def onboarding_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if not city:
        await ask(message, state, "Город не может быть пустым.")
        return
    await state.update_data(city=city)
    await state.set_state(Onboarding.bio)
    await ask(message, state, "Напиши о себе (можно пусто).", reply_markup=kb_bio_skip())


@router.message(Onboarding.bio)
async def onboarding_bio(message: Message, state: FSMContext):
    bio = (message.text or "").strip()
    if bio == "📝 Оставить пустым":
        bio = ""
    await state.update_data(bio=bio)
    await state.set_state(Onboarding.media)
    await ask(message, state, "Добавь до 3 фото или видео.", reply_markup=kb_media())


@router.message(Onboarding.media, F.photo)
async def onboarding_media_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    media = list(data.get("media") or [])
    if len(media) >= 3:
        await ask(message, state, "Уже добавлено 3. Нажми «✅ Готово».", reply_markup=kb_media())
        return
    fid = message.photo[-1].file_id
    media.append({"type": "photo", "file_id": fid})
    await state.update_data(media=media)
    if len(media) >= 3:
        await ask(message, state, "Добавлено 3/3. Нажми «✅ Готово».", reply_markup=kb_media())
    else:
        await ask(message, state, f"Добавлено: {len(media)}/3.", reply_markup=kb_media())


@router.message(Onboarding.media, F.video)
async def onboarding_media_video(message: Message, state: FSMContext):
    data = await state.get_data()
    media = list(data.get("media") or [])
    if len(media) >= 3:
        await ask(message, state, "Уже добавлено 3. Нажми «✅ Готово».", reply_markup=kb_media())
        return
    fid = message.video.file_id
    media.append({"type": "video", "file_id": fid})
    await state.update_data(media=media)
    if len(media) >= 3:
        await ask(message, state, "Добавлено 3/3. Нажми «✅ Готово».", reply_markup=kb_media())
    else:
        await ask(message, state, f"Добавлено: {len(media)}/3.", reply_markup=kb_media())


@router.message(Onboarding.media, F.text.in_({"➕ Добавить ещё", "✅ Готово", "⏭️ Пропустить"}))
async def onboarding_media_controls(message: Message, state: FSMContext, cfg: Config, session_factory, cache: ProfileCache | None):
    data = await state.get_data()
    media = list(data.get("media") or [])

    if message.text == "➕ Добавить ещё":
        if len(media) >= 3:
            await ask(message, state, "Уже добавлено 3. Нажми «✅ Готово».", reply_markup=kb_media())
        else:
            await ask(message, state, "Отправь фото или видео.", reply_markup=kb_media())
        return

    if message.text == "⏭️ Пропустить":
        media = []

    await cleanup_pair(message, state)
    data = await state.get_data()

    payload = {
        "tg_id": message.from_user.id,
        "username": message.from_user.username,
        "full_name": data["full_name"],
        "age": data["age"],
        "city": data["city"],
        "gender": None,
        "bio": data.get("bio") or "",
        "interests": [],
        "pref_age_min": max(18, int(data["age"]) - 3),
        "pref_age_max": min(100, int(data["age"]) + 3),
        "pref_gender": None,
        "pref_city": data["city"],
        "media": media,
        "primary_score": 0.0,
        "behavior_score": 0.0,
        "combined_score": 0.0,
        "referral_score": 0.0,
        "rating_score": cfg.rating_initial,
        "likes_count": 0,
        "dislikes_count": 0,
        "matches_count": 0,
        "dialogs_count": 0,
        "referrals_count": 0,
        "referred_by": data.get("referred_by"),
    }

    primary = compute_primary_score(payload, cfg)
    behavior = compute_behavior_score(payload)
    payload["primary_score"] = primary
    payload["behavior_score"] = behavior
    payload["combined_score"] = compute_combined_score(payload, cfg)

    async with session_factory() as session:
        await upsert_profile(session, payload)
        await session.commit()
        if cache:
            await cache.set_profile(message.from_user.id, payload)

    await state.set_state(None)
    sent = await message.answer("Анкета создана.", reply_markup=kb_main())
    await state.update_data(last_menu_message_id=sent.message_id, last_card_message_id=None, last_bot_message_id=None)


@router.message(F.text == "🏠 Домой")
async def home(message: Message, state: FSMContext):
    await state.set_state(None)
    await send_menu(message, state)


@router.message(F.text == "👤 Моя анкета")
async def my_profile(message: Message, state: FSMContext, session_factory, cache: ProfileCache | None):
    await cleanup_all(message, state)
    async with session_factory() as session:
        profile = await get_profile(session, message.from_user.id)
    if not profile:
        if cache:
            await cache.del_profile(message.from_user.id)
        sent = await message.answer("Анкеты нет. Напиши /start.", reply_markup=kb_main())
        await state.update_data(last_menu_message_id=sent.message_id)
        return
    p = _profile_to_dict(profile)
    if cache:
        await cache.set_profile(message.from_user.id, p)
    sent = await _send_profile_one_message(message, p, reply_markup=kb_profile_manage())
    if isinstance(sent, list):
        await state.update_data(last_card_message_ids=[m.message_id for m in sent], last_card_message_id=None)
    else:
        await state.update_data(last_card_message_id=sent.message_id, last_card_message_ids=None)


@router.message(F.text == "✏️ Изменить анкету")
async def edit_profile(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Onboarding.full_name)
    await state.update_data(media=[])
    default_name = message.from_user.full_name or "Имя"
    await ask(message, state, "Как тебя зовут?", reply_markup=kb_name_default(default_name))


@router.message(F.text == "🗑️ Удалить анкету")
async def delete_profile_ask(message: Message, state: FSMContext):
    await ask(message, state, "Точно удалить анкету?", reply_markup=kb_confirm_delete())
    await state.update_data(pending_delete=True)


@router.message(F.text.in_({"✅ Да, удалить", "❌ Отмена"}))
async def delete_profile_confirm(message: Message, state: FSMContext, session_factory, cache: ProfileCache | None):
    data = await state.get_data()
    if not data.get("pending_delete"):
        return

    if message.text == "❌ Отмена":
        await cleanup_all(message, state)
        await state.update_data(pending_delete=False)
        sent = await message.answer("Отменено.", reply_markup=kb_main())
        await state.update_data(last_menu_message_id=sent.message_id)
        return

    await cleanup_all(message, state)
    async with session_factory() as session:
        await delete_profile(session, message.from_user.id)
        await session.commit()
    if cache:
        await cache.del_profile(message.from_user.id)
        await cache.del_candidate(message.from_user.id)
    await state.clear()
    sent = await message.answer("Анкета удалена.", reply_markup=kb_main())
    await state.update_data(last_menu_message_id=sent.message_id)


@router.message(F.text == "💘 Мэтчи")
async def matches(message: Message, state: FSMContext, session_factory, cache: ProfileCache | None):
    await cleanup_all(message, state)
    async with session_factory() as session:
        me = await get_profile(session, message.from_user.id)
        if not me:
            if cache:
                await cache.del_profile(message.from_user.id)
            sent = await message.answer("Сначала создай анкету через /start.", reply_markup=kb_main())
            await state.update_data(last_menu_message_id=sent.message_id)
            return
        profiles = await get_matches(session, message.from_user.id)

    if not profiles:
        sent = await message.answer("Пока мэтчей нет.", reply_markup=kb_main())
        await state.update_data(last_menu_message_id=sent.message_id)
        return

    lines = ["💘 Твои мэтчи:"]
    for p in profiles[:20]:
        username = p.username
        contact = f"@{username}" if username else f"tg://user?id={int(p.tg_id)}"
        lines.append(f"- {p.full_name}, {p.age}, {p.city} — {contact}")
    sent = await message.answer("\n".join(lines), reply_markup=kb_main())
    await state.update_data(last_menu_message_id=sent.message_id)


@router.message(F.text == "📈 Ранг")
async def rank(message: Message, state: FSMContext, session_factory):
    await cleanup_all(message, state)
    async with session_factory() as session:
        info = await get_rank_info(session, message.from_user.id)
    if not info:
        sent = await message.answer("Сначала создай анкету через /start.", reply_markup=kb_main())
        await state.update_data(last_menu_message_id=sent.message_id)
        return

    text = (
        f"📈 Ранг: {info['position']} из {info['total']}\n\n"
        f"Уровень 1 (первичный): {round(info['primary_score'], 1)}\n"
        f"Уровень 2 (поведенческий): {round(info['behavior_score'], 1)}\n"
        f"Рефералы: {round(info['referral_score'], 1)}\n"
        f"Итог (комбинированный): {round(info['combined_score'], 1)}"
    )
    sent = await message.answer(text, reply_markup=kb_main())
    await state.update_data(last_menu_message_id=sent.message_id)


@router.message(F.text == "👀 Смотреть анкеты")
async def start_viewing(message: Message, state: FSMContext, cfg: Config, session_factory, cache: ProfileCache | None):
    await cleanup_all(message, state)
    async with session_factory() as session:
        viewer = await get_profile(session, message.from_user.id)
        if not viewer:
            if cache:
                await cache.del_profile(message.from_user.id)
                await cache.del_candidate(message.from_user.id)
                await cache.clear_queue(message.from_user.id)
            sent = await message.answer("Сначала создай анкету через /start.", reply_markup=kb_main())
            await state.update_data(last_menu_message_id=sent.message_id)
            return

        if cache:
            await cache.clear_queue(message.from_user.id)

        candidate = await _pick_next_for_viewer(session, cfg, viewer, cache)

        if not candidate:
            await state.set_state(None)
            sent = await message.answer("Анкеты закончились.", reply_markup=kb_main())
            await state.update_data(last_menu_message_id=sent.message_id)
            return

        await state.set_state(Viewing.active)
        await state.update_data(current_target_id=int(candidate.tg_id))
        c = _profile_to_dict(candidate)

    await show_card(message, state, c, reply_markup=kb_viewing())


@router.message(Viewing.active, F.text.in_({"❤️ Лайк", "💔 Дизлайк", "🏠 Домой"}))
async def viewing_vote(message: Message, state: FSMContext, cfg: Config, session_factory, cache: ProfileCache | None, publisher=None):
    if message.text == "🏠 Домой":
        await home(message, state)
        return

    data = await state.get_data()
    target_id = data.get("current_target_id")
    if not target_id:
        await home(message, state)
        return

    await cleanup_all(message, state)

    async with session_factory() as session:
        viewer = await get_profile(session, message.from_user.id)
        if not viewer:
            await session.rollback()
            await state.clear()
            sent = await message.answer("Сначала создай анкету через /start.", reply_markup=kb_main())
            await state.update_data(last_menu_message_id=sent.message_id)
            return

        matched = False
        if message.text == "❤️ Лайк":
            matched = await vote_like(session, cfg, int(viewer.tg_id), int(target_id), publisher=publisher)
        else:
            await vote_dislike(session, cfg, int(viewer.tg_id), int(target_id), publisher=publisher)

        target_profile = None
        if matched:
            target_profile = await get_profile(session, int(target_id))

        candidate = await _pick_next_for_viewer(session, cfg, viewer, cache)
        await session.commit()

    if cache:
        await cache.del_candidate(message.from_user.id)
        await cache.del_profile(message.from_user.id)
        await cache.del_profile(int(target_id))

    if matched:
        try:
            if target_profile:
                viewer_dict = _profile_to_dict(viewer)
                target_dict = _profile_to_dict(target_profile)
                await _send_profile_one_message(message, target_dict, include_contact=True)
                await _send_profile_one_message_to_chat(message.bot, int(target_id), viewer_dict, include_contact=True)
        except Exception:
            log.exception("Не удалось отправить уведомление о мэтче")

    if not candidate:
        await state.clear()
        sent = await message.answer("Анкеты закончились.", reply_markup=kb_main())
        await state.update_data(last_menu_message_id=sent.message_id)
        return

    await state.update_data(current_target_id=int(candidate.tg_id))
    c = _profile_to_dict(candidate)
    await show_card(message, state, c, reply_markup=kb_viewing())


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "tg_id": int(p.tg_id),
        "username": p.username,
        "full_name": p.full_name,
        "age": p.age,
        "city": p.city,
        "bio": p.bio,
        "media": p.media,
        "rating_score": float(p.rating_score),
        "likes_count": int(p.likes_count),
        "dislikes_count": int(p.dislikes_count),
        "matches_count": int(p.matches_count),
    }
