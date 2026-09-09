from __future__ import annotations

import asyncio
import sys

from weixin_agent import Agent, ChatRequest, ChatResponse, login, start


class EchoAgent(Agent):
    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(text=f"You said: {request.text}" + '\r\n'+'aaa')


async def main() -> None:
    argv = sys.argv
    command = argv[1] if len(argv) > 1 else ""

    if command == "login":
        await login()
        return

    if command == "start":
        agent = EchoAgent()
        await start(agent)
        return

    raise SystemExit(
        "Usage:\n  python -m examples.echo_bot login\n  python -m examples.echo_bot start"
    )


if __name__ == "__main__":
    asyncio.run(main())
