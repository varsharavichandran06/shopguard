"""The ShopGuard agent and a Conversation wrapper used by the CLI, the UI and the eval runner.

    async with Conversation(db_path, session_path) as convo:
        turn = await convo.send("hi, I want to return my jacket")
        print(turn.reply, turn.tool_calls)

One MCP server process per Conversation context. The verified user lives in a small
JSON session file, so the UI can open a fresh context per turn without losing identity.
"""
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from agents import (
    Agent,
    InputGuardrailTripwireTriggered,
    ModelSettings,
    RunConfig,
    Runner,
    function_tool,
)
from agents.mcp import MCPServerStdio

from . import config
from .config import AGENT_MODEL, AGENT_REASONING, ROOT
from .guardrails import SAFE_REPLIES, shopguard_guard
from .prompts import ESCALATION_PROMPT, PROMPT_ONLY_RULES, SUPPORT_PROMPT
from .search import search_policy_text


@function_tool
def search_policy(query: str) -> str:
    """Search the store policy. Returns up to 3 passages with doc ids to cite, or NO_RELEVANT_POLICY."""
    return search_policy_text(query, k=3)


def _model_settings(model) -> ModelSettings:
    if not isinstance(model, str):  # a test model object
        return ModelSettings()
    if config.is_reasoning_model(model):
        from openai.types.shared import Reasoning

        return ModelSettings(reasoning=Reasoning(effort=AGENT_REASONING))
    return ModelSettings(temperature=0.2)


def build_agent(mcp_server, model: str = AGENT_MODEL, rules_mode: str = "on") -> Agent:
    escalation = Agent(
        name="Escalation",
        handoff_description="Hand the case to a human teammate.",
        instructions=ESCALATION_PROMPT,
        model=model,
        model_settings=_model_settings(model),
    )
    instructions = SUPPORT_PROMPT + (PROMPT_ONLY_RULES if rules_mode == "off" else "")
    return Agent(
        name="Support",
        instructions=instructions,
        model=model,
        model_settings=_model_settings(model),
        mcp_servers=[mcp_server],
        tools=[search_policy],
        handoffs=[escalation],
        input_guardrails=[shopguard_guard],
    )


def make_mcp_server(db_path: str | Path, session_path: str | Path, rules_mode: str = "on") -> MCPServerStdio:
    env = {
        **os.environ,
        "DB_PATH": str(db_path),
        "SESSION_PATH": str(session_path),
        "SHOPGUARD_RULES": rules_mode,
        "PYTHONPATH": str(ROOT),
    }
    return MCPServerStdio(
        name="orders",
        params={"command": sys.executable, "args": ["-m", "shopguard.mcp_server"], "env": env, "cwd": str(ROOT)},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    )


@dataclass
class Turn:
    reply: str
    tool_calls: list[dict] = field(default_factory=list)
    escalated: bool = False
    guardrail: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


def _extract_tool_calls(result) -> list[dict]:
    calls, by_id = [], {}
    for item in result.new_items:
        raw = getattr(item, "raw_item", None)
        if item.type == "tool_call_item":
            name = getattr(raw, "name", None) or (raw.get("name") if isinstance(raw, dict) else None)
            args = getattr(raw, "arguments", None) or (raw.get("arguments") if isinstance(raw, dict) else None)
            call_id = getattr(raw, "call_id", None) or (raw.get("call_id") if isinstance(raw, dict) else None)
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                pass
            entry = {"tool": name, "args": args, "output": None}
            calls.append(entry)
            if call_id:
                by_id[call_id] = entry
        elif item.type == "tool_call_output_item":
            call_id = raw.get("call_id") if isinstance(raw, dict) else getattr(raw, "call_id", None)
            out = item.output if isinstance(item.output, str) else json.dumps(item.output, default=str)
            try:  # MCP outputs arrive wrapped as {"type": "text", "text": ...}
                wrapped = json.loads(out)
                if isinstance(wrapped, dict) and wrapped.get("type") == "text":
                    out = wrapped["text"]
            except (json.JSONDecodeError, TypeError):
                pass
            out = out.replace("Error executing tool ", "ERROR in ")
            if call_id in by_id:
                by_id[call_id]["output"] = out[:2000]
        elif item.type == "handoff_output_item":
            calls.append({"tool": "handoff", "args": {"to": "Escalation"}, "output": None})
    return calls


class Conversation:
    """Keeps the chat history and runs one agent turn per customer message."""

    def __init__(
        self,
        db_path: str | Path,
        session_path: str | Path,
        history: list | None = None,
        conversation_id: str | None = None,
        model: str = AGENT_MODEL,
        rules_mode: str = "on",
        trace_metadata: dict | None = None,
    ):
        self.db_path, self.session_path = db_path, session_path
        self.history: list = list(history or [])
        self.id = conversation_id or uuid.uuid4().hex[:12]
        self.model, self.rules_mode = model, rules_mode
        self.trace_metadata = {"conversation_id": self.id, **(trace_metadata or {})}
        self.escalated = False
        self._server = None
        self._agent = None

    async def __aenter__(self) -> "Conversation":
        self._server = make_mcp_server(self.db_path, self.session_path, self.rules_mode)
        await self._server.connect()
        self._agent = build_agent(self._server, self.model, self.rules_mode)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._server:
            await self._server.cleanup()

    async def send(self, message: str) -> Turn:
        start = time.time()
        inp = self.history + [{"role": "user", "content": message}]
        run_config = RunConfig(
            workflow_name="shopguard",
            group_id=self.id,
            trace_metadata={k: str(v) for k, v in self.trace_metadata.items()},
        )
        try:
            result = await Runner.run(self._agent, inp, max_turns=15, run_config=run_config)
        except InputGuardrailTripwireTriggered as e:
            info = e.guardrail_result.output.output_info or {}
            kind = info.get("kind", "injection")
            reply = SAFE_REPLIES.get(kind, SAFE_REPLIES["injection"])
            # Keep the history clean: do not store a card number in the transcript.
            shown = "[message removed: card number]" if kind == "card_number" else message
            self.history = self.history + [{"role": "user", "content": shown}, {"role": "assistant", "content": reply}]
            return Turn(reply=reply, guardrail=kind, seconds=time.time() - start)

        self.history = result.to_input_list()
        usage = result.context_wrapper.usage
        self.escalated = self.escalated or result.last_agent.name == "Escalation"
        return Turn(
            reply=str(result.final_output or ""),
            tool_calls=_extract_tool_calls(result),
            escalated=self.escalated,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            seconds=time.time() - start,
        )
