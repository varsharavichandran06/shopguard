"""Tracing.

By default the OpenAI Agents SDK sends a trace of every run (each model call, tool call,
handoff and guardrail) to the Traces page of your OpenAI dashboard. Nothing to set up.

Optional: send the same traces to Langfuse through OpenTelemetry.
  pip install -r requirements-tracing.txt
  set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST in .env
Check the Langfuse docs for the current OpenAI Agents integration if this import changes.
"""
import os

_done = False


def setup_tracing() -> str:
    global _done
    if _done:
        return "already set"
    _done = True
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return "openai"
    try:
        from langfuse import get_client
        from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

        OpenAIAgentsInstrumentor().instrument()
        client = get_client()
        return "langfuse" if client.auth_check() else "langfuse auth failed"
    except Exception as e:
        print(f"[tracing] Langfuse not enabled: {e}")
        return "openai"
