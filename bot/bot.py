"""
UniProxy Telegram Bot
Commands:
  /start          — welcome
  /status         — dashboard stats
  /users          — list users
  /adduser        — create user (wizard)
  /deluser <id>   — delete user
  /nodes          — list nodes
  /checknodes     — trigger health check
  /sub <user_id>  — get subscription link
  /logs           — last 50 log lines
  /restart <svc>  — restart xray/sing-box
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import httpx
from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, BotCommand, TelegramObject
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("uniproxy-bot")

def parse_admin_ids(raw: str) -> frozenset[int]:
    try:
        identifiers = frozenset(int(value.strip()) for value in raw.split(",") if value.strip())
        if any(identifier <= 0 for identifier in identifiers):
            raise ValueError
        return identifiers
    except ValueError:
        raise RuntimeError(
            "TELEGRAM_ADMIN_IDS must contain comma-separated positive numeric user IDs"
        ) from None


TOKEN    = os.environ.get("TELEGRAM_TOKEN", "")
API_URL  = os.environ.get("API_URL", "http://backend:8000")
ADMIN_IDS = parse_admin_ids(os.environ.get("TELEGRAM_ADMIN_IDS", ""))
BOT_USER  = os.environ.get("BOT_API_USER", "admin")
BOT_PASS  = os.environ.get("BOT_API_PASS", os.environ.get("MASTER_PASSWORD", "admin"))

dp  = Dispatcher()

###############################################################################
# AUTH
###############################################################################
_jwt_token: Optional[str] = None

async def get_token() -> str:
    global _jwt_token
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as c:
        r = await c.post("/api/auth/login",
                         data={"username": BOT_USER, "password": BOT_PASS},
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        r.raise_for_status()
        _jwt_token = r.json()["access_token"]
    return _jwt_token

async def api(method: str, path: str, **kwargs) -> dict:
    global _jwt_token
    if not _jwt_token:
        await get_token()
    headers = {"Authorization": f"Bearer {_jwt_token}"}
    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
        fn = getattr(c, method)
        r  = await fn(path, headers=headers, **kwargs)
        if r.status_code == 401:
            await get_token()
            headers["Authorization"] = f"Bearer {_jwt_token}"
            r = await fn(path, headers=headers, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}


###############################################################################
# ACCESS GUARD
###############################################################################
class AdminAccessMiddleware(BaseMiddleware):
    """Guard the update boundary, including callbacks and active FSM steps."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor = data.get("event_from_user")
        if actor is not None and actor.id in ADMIN_IDS:
            return await handler(event, data)

        callback = getattr(event, "callback_query", None)
        message = getattr(event, "message", None)
        if callback is not None:
            await callback.answer("Access denied.", show_alert=True)
        elif message is not None:
            await message.answer("Access denied.")
        return None


dp.update.outer_middleware(AdminAccessMiddleware())


###############################################################################
# FSM — Add User Wizard
###############################################################################
class AddUserFSM(StatesGroup):
    username   = State()
    password   = State()
    traffic_gb = State()


###############################################################################
# /start
###############################################################################
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Status",  callback_data="status"),
         InlineKeyboardButton(text="🖥 Nodes",   callback_data="nodes")],
        [InlineKeyboardButton(text="👥 Users",   callback_data="users"),
         InlineKeyboardButton(text="📋 Logs",    callback_data="logs")],
    ])
    await msg.answer(
        "🔰 *UniProxy Bot*\nUnified proxy management at your fingertips.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


###############################################################################
# /status  →  dashboard stats
###############################################################################
@dp.message(Command("status"))
@dp.callback_query(F.data == "status")
async def cmd_status(event):
    msg = event if isinstance(event, Message) else event.message
    try:
        d = await api("get", "/api/stats/dashboard")
        sys = d.get("system", {})
        text = (
            f"📊 *Dashboard*\n\n"
            f"👥 Users: `{d['users']['active']}/{d['users']['total']}`\n"
            f"🖥 Nodes: `{d['nodes']['online']}/{d['nodes']['total']}`\n"
            f"🔌 Protocols: `{d['protocols']['total']}`\n\n"
            f"🖧 CPU:  `{sys.get('cpu_pct','?')}%`\n"
            f"💾 RAM:  `{sys.get('ram_used_gb','?')}/{sys.get('ram_total_gb','?')} GB ({sys.get('ram_pct','?')}%)`\n"
            f"💿 Disk: `{sys.get('disk_used_gb','?')}/{sys.get('disk_total_gb','?')} GB ({sys.get('disk_pct','?')}%)`\n\n"
            f"⬇ Recv: `{d['traffic']['in_bytes']/1e9:.2f} GB` | "
            f"⬆ Sent: `{d['traffic']['out_bytes']/1e9:.2f} GB`"
        )
    except Exception as e:
        text = f"❌ Error: {e}"
    await msg.answer(text, parse_mode="Markdown")


###############################################################################
# /nodes
###############################################################################
@dp.message(Command("nodes"))
@dp.callback_query(F.data == "nodes")
async def cmd_nodes(event):
    msg = event if isinstance(event, Message) else event.message
    try:
        nodes = await api("get", "/api/nodes")
        if not nodes:
            await msg.answer("No nodes configured.")
            return
        lines = ["🖥 *Nodes:*\n"]
        for n in nodes:
            icon  = "🟢" if n["status"] == "online" else "🔴"
            lat   = f"{n['latency_ms']:.0f}ms" if n.get("latency_ms") else "N/A"
            protos = ", ".join(p["name"] for p in n.get("protocols", []))
            lines.append(f"{icon} *{n['name']}* (`{n['host']}`)\n   📶 {lat} | {protos or 'no protocols'}")
        await msg.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /checknodes
###############################################################################
@dp.message(Command("checknodes"))
async def cmd_check_nodes(msg: Message):
    await msg.answer("🔄 Running health check on all nodes…")
    try:
        await api("post", "/api/nodes/check-all")
        await msg.answer("✅ Health check triggered. Use /nodes to see results.")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /users
###############################################################################
@dp.message(Command("users"))
@dp.callback_query(F.data == "users")
async def cmd_users(event):
    msg = event if isinstance(event, Message) else event.message
    try:
        users = await api("get", "/api/users")
        if not users:
            await msg.answer("No users.")
            return
        lines = ["👥 *Users:*\n"]
        for u in users[:20]:
            status = "✅" if u["is_active"] and not u["is_expired"] else "❌"
            trf    = f"{u['traffic_used_gb']:.1f}/{u['traffic_limit_gb'] or '∞'} GB"
            lines.append(f"{status} `{u['id']}` *{u['username']}* — {trf}")
        if len(users) > 20:
            lines.append(f"\n… and {len(users)-20} more")
        await msg.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /adduser — wizard
###############################################################################
@dp.message(Command("adduser"))
async def cmd_adduser_start(msg: Message, state: FSMContext):
    await state.set_state(AddUserFSM.username)
    await msg.answer("👤 Enter *username* for the new user:", parse_mode="Markdown")

@dp.message(AddUserFSM.username)
async def adduser_username(msg: Message, state: FSMContext):
    await state.update_data(username=msg.text.strip())
    await state.set_state(AddUserFSM.password)
    await msg.answer("🔑 Enter *password*:", parse_mode="Markdown")

@dp.message(AddUserFSM.password)
async def adduser_password(msg: Message, state: FSMContext):
    await state.update_data(password=msg.text.strip())
    await state.set_state(AddUserFSM.traffic_gb)
    await msg.answer("📦 Traffic limit in GB (0 = unlimited):")

@dp.message(AddUserFSM.traffic_gb)
async def adduser_traffic(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        gb = float(msg.text.strip())
    except ValueError:
        await msg.answer("❌ Invalid number. Try again:")
        return
    await state.clear()
    try:
        u = await api("post", "/api/users", json={
            "username": data["username"],
            "password": data["password"],
            "traffic_limit_gb": gb,
        })
        await msg.answer(
            f"✅ User *{u['username']}* created (ID `{u['id']}`)\n"
            f"Traffic: {'∞' if gb == 0 else f'{gb} GB'}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer(f"❌ Error: {e}")


###############################################################################
# /deluser <id>
###############################################################################
@dp.message(Command("deluser"))
async def cmd_deluser(msg: Message):
    parts = msg.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await msg.answer("Usage: `/deluser <id>`", parse_mode="Markdown")
        return
    uid = int(parts[1])
    try:
        await api("delete", f"/api/users/{uid}")
        await msg.answer(f"✅ User `{uid}` deleted.", parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /sub <user_id>
###############################################################################
@dp.message(Command("sub"))
async def cmd_sub(msg: Message):
    parts = msg.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await msg.answer("Usage: `/sub <user_id>`", parse_mode="Markdown")
        return
    # Create a singbox subscription for the user
    # (requires the bot to act as that user — for simplicity, list all subs)
    try:
        subs = await api("get", "/api/subscriptions")
        user_subs = [s for s in subs if s["user_id"] == int(parts[1])]
        if not user_subs:
            await msg.answer("No subscriptions for this user. Ask them to create one via the panel.")
            return
        lines = [f"📋 *Subscriptions for user {parts[1]}:*\n"]
        for s in user_subs:
            lines.append(f"• [{s['format']}]({s['url']})")
        await msg.answer("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /logs
###############################################################################
@dp.message(Command("logs"))
@dp.callback_query(F.data == "logs")
async def cmd_logs(event):
    msg = event if isinstance(event, Message) else event.message
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=15) as c:
            if not _jwt_token:
                await get_token()
            r = await c.get("/api/system/logs/uniproxy?lines=30",
                            headers={"Authorization": f"Bearer {_jwt_token}"})
            r.raise_for_status()
            text = r.text or "No logs"
        # Telegram message limit: 4096 chars
        if len(text) > 3800:
            text = "…\n" + text[-3800:]
        await msg.answer(f"```\n{text}\n```", parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /cert — TLS status + renew
###############################################################################
@dp.message(Command("cert"))
async def cmd_cert(msg: Message):
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=20) as c:
            if not _jwt_token:
                await get_token()
            r = await c.get("/api/system/cert/status",
                            headers={"Authorization": f"Bearer {_jwt_token}"})
            r.raise_for_status()
            d = r.json()
        if not d.get("valid"):
            await msg.answer(
                f"🔴 *{d.get('domain','?')}* — invalid\n`{d.get('error','')}`\n\n"
                f"Renewing…", parse_mode="Markdown"
            )
            async with httpx.AsyncClient(base_url=API_URL, timeout=60) as c:
                r = await c.post("/api/system/cert/renew",
                                 headers={"Authorization": f"Bearer {_jwt_token}"})
                out = r.json()
            await msg.answer(f"```\n{out.get('output','')[:3500]}\n```", parse_mode="Markdown")
        else:
            await msg.answer(
                f"🟢 *{d.get('domain','?')}* — valid\n"
                f"Not before: `{d.get('not_before','?')}`\n"
                f"Not after:  `{d.get('not_after','?')}`",
                parse_mode="Markdown",
            )
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# /restart <xray|sing-box>
###############################################################################
@dp.message(Command("restart"))
async def cmd_restart(msg: Message):
    parts = msg.text.split()
    if len(parts) != 2 or parts[1] not in ("xray", "sing-box", "singbox"):
        await msg.answer("Usage: `/restart xray` or `/restart sing-box`", parse_mode="Markdown")
        return
    svc = "singbox" if parts[1] in ("singbox","sing-box") else "xray"
    try:
        await api("post", f"/api/system/{svc}/restart")
        await msg.answer(f"✅ `{svc}` restarted.", parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"❌ {e}")


###############################################################################
# CALLBACK FALLBACK
###############################################################################
@dp.callback_query()
async def cb_fallback(cb: CallbackQuery):
    await cb.answer("Unknown action")


###############################################################################
# MAIN
###############################################################################
async def main():
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not set — bot disabled")
        return
    if not ADMIN_IDS:
        raise RuntimeError("TELEGRAM_ADMIN_IDS must contain at least one admin before starting the bot")

    bot = Bot(token=TOKEN)

    # Register bot commands
    await bot.set_my_commands([
        BotCommand(command="start",      description="Main menu"),
        BotCommand(command="status",     description="Dashboard stats"),
        BotCommand(command="nodes",      description="List nodes"),
        BotCommand(command="checknodes", description="Health check all nodes"),
        BotCommand(command="users",      description="List users"),
        BotCommand(command="adduser",    description="Create new user"),
        BotCommand(command="deluser",    description="Delete user by ID"),
        BotCommand(command="sub",        description="Get subscription for user"),
        BotCommand(command="logs",       description="View recent logs"),
        BotCommand(command="cert",       description="TLS certificate status / renew"),
        BotCommand(command="restart",    description="Restart xray or sing-box"),
    ])

    logger.info("UniProxy bot started")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
