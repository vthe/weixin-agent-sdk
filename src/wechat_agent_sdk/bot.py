"""Main bot module: login, logout, start, is_logged_in."""

import os
import subprocess
import urllib.parse
from dataclasses import dataclass
from typing import Optional, Protocol

from wechat_agent_sdk.auth.accounts import (
    DEFAULT_BASE_URL,
    clear_all_weixin_accounts,
    list_weixin_account_ids,
    resolve_weixin_account,
    save_weixin_account,
    register_weixin_account_id,
    normalize_account_id,
)
from wechat_agent_sdk.auth.login_qr import DEFAULT_ILINK_BOT_TYPE, start_weixin_login_with_qr, wait_for_weixin_login
from wechat_agent_sdk.monitor.monitor import monitor_weixin_provider
from wechat_agent_sdk.util.logger import logger


@dataclass
class LoginOptions:
    base_url: Optional[str] = None
    log: Optional[callable] = None


@dataclass
class StartOptions:
    account_id: Optional[str] = None
    abort_signal: Optional[object] = None
    log: Optional[callable] = None


class Agent(Protocol):
    async def chat(self, request) -> None:
        ...


async def login(opts: Optional[LoginOptions] = None) -> str:
    """Interactive QR-code login. Prints the QR code to the terminal and waits for the user to scan it with WeChat."""
    log_fn = opts.log if opts and opts.log else print
    api_base_url = opts.base_url if opts and opts.base_url else DEFAULT_BASE_URL

    log_fn("正在启动微信扫码登录...")

    start_result = await start_weixin_login_with_qr(
        api_base_url=api_base_url,
        bot_type=DEFAULT_ILINK_BOT_TYPE,
    )

    if not start_result.qrcodeUrl:
        raise Exception(start_result.message)

    log_fn("\n使用微信扫描以下二维码，以完成连接：\n")

    try:
        import qrcode
        import tempfile
        import sys

        qr_url = start_result.qrcodeUrl
        img = qrcode.make(qr_url)

        pixels = img.load()
        width, height = img.size
        block = "██" if sys.platform != "win32" else "##"
        space = "  " if sys.platform != "win32" else "  "

        log_fn("\n使用微信扫描以下二维码：\n")
        for y in range(height):
            row = ""
            for x in range(width):
                if pixels[x, y]:
                    row += block
                else:
                    row += space
            log_fn(row)
        log_fn("\n")

        temp_file = os.path.join(tempfile.gettempdir(), "weixin_qrcode.png")
        img.save(temp_file)
        log_fn(f"二维码已保存到: {temp_file}")

        if sys.platform == "darwin":
            subprocess.run(["open", temp_file], check=True)
        elif sys.platform == "win32":
            os.startfile(temp_file)
        else:
            subprocess.run(["xdg-open", temp_file], check=True)
    except Exception as e:
        log_fn(f"无法显示二维码: {e}")
        log_fn(f"二维码链接: {start_result.qrcodeUrl}")

    log_fn("\n等待扫码...\n")

    wait_result = await wait_for_weixin_login(
        session_key=start_result.sessionKey,
        api_base_url=api_base_url,
        timeout_ms=480_000,
        bot_type=DEFAULT_ILINK_BOT_TYPE,
    )

    if not wait_result.connected or not wait_result.botToken or not wait_result.accountId:
        raise Exception(wait_result.message)

    normalized_id = normalize_account_id(wait_result.accountId)
    save_weixin_account(normalized_id, {
        "token": wait_result.botToken,
        "baseUrl": wait_result.baseUrl or "",
        "userId": wait_result.userId or "",
    })
    register_weixin_account_id(normalized_id)

    log_fn("\n✅ 与微信连接成功！")
    return normalized_id


def logout(opts: Optional[dict] = None) -> None:
    """Remove all stored WeChat account credentials."""
    log_fn = (opts or {}).get("log") or print
    ids = list_weixin_account_ids()
    if not ids:
        log_fn("当前没有已登录的账号")
        return
    clear_all_weixin_accounts()
    log_fn("✅ 已退出登录")


def is_logged_in() -> bool:
    """Check whether at least one WeChat account is logged in and configured."""
    ids = list_weixin_account_ids()
    if not ids:
        return False
    account = resolve_weixin_account(ids[0])
    return account.configured


async def start(agent: Agent, opts: Optional[StartOptions] = None) -> None:
    """Start the bot — long-polls for new messages and dispatches them to the agent."""
    log_fn = (opts.log if opts else None) or (lambda msg: print(msg))

    account_id = (opts.account_id if opts else None) if opts else None
    if not account_id:
        ids = list_weixin_account_ids()
        if not ids:
            raise Exception("没有已登录的账号，请先运行 login")
        account_id = ids[0]
        if len(ids) > 1:
            log_fn(f"[weixin] 检测到多个账号，使用第一个: {account_id}")

    account = resolve_weixin_account(account_id)
    if not account.configured:
        raise Exception(f"账号 {account_id} 未配置 (缺少 token)，请先运行 login")

    log_fn(f"[weixin] 启动 bot, account={account.account_id}")

    await monitor_weixin_provider(
        base_url=account.base_url,
        cdn_base_url=account.cdn_base_url,
        token=account.token,
        account_id=account.account_id,
        agent=agent,
        abort_signal=opts.abort_signal if opts else None,
        log=log_fn,
    )
