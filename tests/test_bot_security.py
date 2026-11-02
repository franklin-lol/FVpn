"""Exercise the real aiogram update pipeline without Telegram or backend I/O."""

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Update


@pytest.fixture
def bot_module(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "123456:fixture-only-telegram-token")
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "7")
    path = Path(__file__).resolve().parents[1] / "bot" / "bot.py"
    spec = importlib.util.spec_from_file_location("fvpn_bot_security_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "api", AsyncMock(return_value=[]))
    return module


def message_update(text, user_id=42):
    return Update.model_validate({
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Fixture"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
            if text.startswith("/") else [],
        },
    })


def callback_update(data, user_id=42):
    return Update.model_validate({
        "update_id": 2,
        "callback_query": {
            "id": "fixture-callback",
            "from": {"id": user_id, "is_bot": False, "first_name": "Fixture"},
            "chat_instance": "fixture-chat",
            "data": data,
            "message": {
                "message_id": 2,
                "date": 1,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 123456, "is_bot": True, "first_name": "Fixture bot"},
                "text": "Menu",
            },
        },
    })


async def feed(module, update, state=None):
    telegram_bot = Bot(token="123456:fixture-only-telegram-token")
    session = AsyncMock(return_value=True)
    telegram_bot.session = session
    context = module.dp.fsm.get_context(bot=telegram_bot, chat_id=42, user_id=42)
    if state is not None:
        await context.set_state(state)
        await context.set_data({"username": "original", "password": "fixture-password"})
    before = (await context.get_state(), await context.get_data())
    try:
        await module.dp.feed_update(telegram_bot, update)
        after = (await context.get_state(), await context.get_data())
    finally:
        await module.dp.storage.close()
        await session.close()
    return before, after, session


@pytest.mark.parametrize("admin_ids", [frozenset(), frozenset({7})])
@pytest.mark.parametrize("command", ["/start", "/status", "/nodes", "/users", "/adduser", "/restart xray"])
def test_message_commands_deny_unlisted_users(bot_module, monkeypatch, admin_ids, command):
    monkeypatch.setattr(bot_module, "ADMIN_IDS", admin_ids)
    before, after, session = asyncio.run(feed(bot_module, message_update(command)))
    assert before == after
    bot_module.api.assert_not_awaited()
    assert session.await_count == 1
    assert session.call_args.args[1].text == "Access denied."


@pytest.mark.parametrize("admin_ids", [frozenset(), frozenset({7})])
@pytest.mark.parametrize("action", ["status", "nodes", "users", "logs", "unknown-action"])
def test_callbacks_deny_unlisted_authors(bot_module, monkeypatch, admin_ids, action):
    monkeypatch.setattr(bot_module, "ADMIN_IDS", admin_ids)
    before, after, session = asyncio.run(feed(bot_module, callback_update(action)))
    assert before == after
    bot_module.api.assert_not_awaited()
    assert session.await_count == 1
    method = session.call_args.args[1]
    assert method.callback_query_id == "fixture-callback"
    assert method.text == "Access denied."
    assert method.show_alert is True


@pytest.mark.parametrize("admin_ids", [frozenset(), frozenset({7})])
@pytest.mark.parametrize("step,text", [("username", "replacement"), ("password", "replacement"), ("traffic_gb", "5")])
def test_unauthorized_fsm_updates_cannot_mutate_state_or_create_users(
    bot_module, monkeypatch, admin_ids, step, text
):
    monkeypatch.setattr(bot_module, "ADMIN_IDS", admin_ids)
    state = getattr(bot_module.AddUserFSM, step)
    before, after, _ = asyncio.run(feed(bot_module, message_update(text), state))
    assert after == before
    bot_module.api.assert_not_awaited()


def test_message_without_an_actor_cannot_reach_handlers(bot_module):
    payload = message_update("/nodes").model_dump(by_alias=True)
    payload["message"]["from"] = None
    update = Update.model_validate(payload)
    _, _, session = asyncio.run(feed(bot_module, update))
    bot_module.api.assert_not_awaited()
    assert session.call_args.args[1].text == "Access denied."


@pytest.mark.parametrize("callback", [False, True])
def test_allowlisted_actor_can_call_backend(bot_module, callback):
    update = callback_update("nodes", 7) if callback else message_update("/nodes", 7)
    asyncio.run(feed(bot_module, update))
    bot_module.api.assert_awaited_once_with("get", "/api/nodes")


def test_startup_rejects_empty_admin_allowlist_before_bot_or_network(bot_module, monkeypatch):
    monkeypatch.setattr(bot_module, "ADMIN_IDS", frozenset())

    def forbidden_bot(*args, **kwargs):
        pytest.fail("startup must reject missing admins before creating the Telegram client")

    monkeypatch.setattr(bot_module, "Bot", forbidden_bot)
    with pytest.raises(RuntimeError, match="TELEGRAM_ADMIN_IDS"):
        asyncio.run(bot_module.main())


@pytest.mark.parametrize("raw", ["not-a-number", "7,-1", "7,0", "7,8.5"])
def test_admin_id_validation_has_a_clear_nonreflective_error(bot_module, raw):
    with pytest.raises(RuntimeError, match="TELEGRAM_ADMIN_IDS") as error:
        bot_module.parse_admin_ids(raw)
    assert raw not in str(error.value)


def test_admin_ids_allow_spaces_and_trailing_commas(bot_module):
    assert bot_module.parse_admin_ids(" 7, 8, , ") == frozenset({7, 8})


def test_missing_token_disables_bot_without_constructing_client(bot_module, monkeypatch):
    monkeypatch.setattr(bot_module, "TOKEN", "")
    monkeypatch.setattr(bot_module, "ADMIN_IDS", frozenset())

    def forbidden_bot(*args, **kwargs):
        pytest.fail("disabled bot must not create the Telegram client")

    monkeypatch.setattr(bot_module, "Bot", forbidden_bot)
    asyncio.run(bot_module.main())
