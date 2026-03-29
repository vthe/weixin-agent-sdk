# WeChat Agent SDK

> **免责声明**: 本项目非微信官方项目，代码由 [@tencent-weixin/openclaw-weixin](https://github.com/tencent-weixin/openclaw-weixin) 改造而来，仅供学习交流使用。

微信 AI Agent 桥接框架 —— 通过简单的 Agent 接口，将任意 AI 后端接入微信。

## Installation (Local Development)

```bash
cd packages/wechat-agent-sdk
pip install -e .
```

Or install from source:

```bash
git clone https://github.com/vthe/weixin-agent-sdk.git
cd weixin-agent-sdk
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
