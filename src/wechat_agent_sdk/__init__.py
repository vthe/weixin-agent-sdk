"""WeChat AI Agent Bridge SDK.

This package provides a simple Agent interface to connect any AI backend to WeChat.
"""

from wechat_agent_sdk.agent.interface import Agent, ChatRequest, ChatResponse
from wechat_agent_sdk.bot import login, logout, start, is_logged_in
from wechat_agent_sdk.bot import LoginOptions, StartOptions

__all__ = [
    "Agent",
    "ChatRequest",
    "ChatResponse",
    "login",
    "logout",
    "start",
    "is_logged_in",
    "LoginOptions",
    "StartOptions",
]
