"""Input guardrail. Runs on every customer message before the main agent.

Two checks:
1. Card numbers (cheap regex, no model call). We never want those in the chat log.
2. Prompt injection, judged by a small fast model. Set GUARDRAIL_LLM=off to skip it.
"""
import json
import os
import re

from agents import Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail

from .config import GUARD_MODEL
from .prompts import GUARD_PROMPT

CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")

SAFE_REPLIES = {
    "card_number": "For your safety, please don't share card numbers here. I never need them. How else can I help with your order?",
    "injection": "I can't change how I work, but I'm happy to help with your order. What do you need?",
}


def last_user_text(inp) -> str:
    if isinstance(inp, str):
        return inp
    for item in reversed(inp):
        if isinstance(item, dict) and item.get("role") == "user":
            content = item.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def looks_like_card(text: str) -> bool:
    for m in CARD_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return True
    return False


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for d in reversed(digits):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
        alt = not alt
    return total % 10 == 0


async def _llm_injection_check(text: str) -> tuple[bool, str]:
    if os.environ.get("GUARDRAIL_LLM", "on") == "off" or not os.environ.get("OPENAI_API_KEY"):
        return False, "skipped"
    from openai import AsyncOpenAI

    try:
        resp = await AsyncOpenAI().chat.completions.create(
            model=GUARD_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": GUARD_PROMPT}, {"role": "user", "content": text[:4000]}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return bool(data.get("injection")), str(data.get("reason", ""))
    except Exception as e:  # fail open: the tools still enforce every rule
        return False, f"guard error: {e}"


@input_guardrail
async def shopguard_guard(ctx: RunContextWrapper, agent: Agent, inp) -> GuardrailFunctionOutput:
    text = last_user_text(inp)
    if looks_like_card(text):
        return GuardrailFunctionOutput(output_info={"kind": "card_number"}, tripwire_triggered=True)
    hit, reason = await _llm_injection_check(text)
    return GuardrailFunctionOutput(output_info={"kind": "injection" if hit else "ok", "reason": reason}, tripwire_triggered=hit)
