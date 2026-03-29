# WeChat Agent SDK

A Python SDK for building WeChat bots with AI agent integration.

> **Note**: This project is a Python version derived from [wong2/weixin-agent-sdk](https://github.com/wong2/weixin-agent-sdk).

## Installation (Local Development)

```bash
cd packages/wechat-agent-sdk
pip install -e .
```

Or install from source:

```bash
git clone https://github.com/yourusername/wechat-agent-sdk.git
cd wechat-agent-sdk
pip install -e .
```

## Quick Start

```python
import asyncio
from dataclasses import dataclass
from wechat_agent_sdk import login, start, Agent, ChatRequest, ChatResponse

@dataclass
class MyAgent:
    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(text=f"Echo: {request.text}")

async def main():
    await login()
    await start(MyAgent())

if __name__ == "__main__":
    asyncio.run(main())
```

## Features

- Simple Agent interface for connecting any AI backend to WeChat
- QR code login support
- Message handling (text, images, files, etc.)
- CDN media upload/download
- Debug mode with slash commands

## License

MIT License
