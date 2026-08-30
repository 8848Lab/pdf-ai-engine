"""Public surface of the AI instruction layer -- resolve_api_key() and
run_instruction() are what webui/main.py calls. See loop.py, tools.py, and
providers/ for the implementation; this package replaces the single-file
webui/ai.py module now that a second provider (beyond Anthropic) makes a
package layout worth the file count. See the design spec's "Architecture"
section.
"""
from webui.ai.loop import run_instruction
from webui.ai.providers.anthropic import resolve_api_key

__all__ = ["run_instruction", "resolve_api_key"]
