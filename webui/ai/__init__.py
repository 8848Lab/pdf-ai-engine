"""Public surface of the AI instruction layer -- resolve_api_key() and
run_instruction() are what webui/main.py calls. See loop.py, tools.py, and
providers/ for the implementation.
"""
from webui.ai.loop import run_instruction
from webui.ai.providers import resolve_api_key

__all__ = ["run_instruction", "resolve_api_key"]
