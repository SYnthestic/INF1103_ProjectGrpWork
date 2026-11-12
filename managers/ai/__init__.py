"""AI Manager: sends a proposal narrative to a language model and returns a
validated, correctly typed audit. One class per module:

    AIClient (abstract)     ai_client.py           "give me a prompt, I give you text"
      OpenRouterClient      openrouter_client.py   the real implementation
    AuditResponseParser     audit_response_parser.py   raw model text -> audit dict
    AIManager               ai_manager.py          uses an AIClient (aggregation),
                                                   owns a parser (composition)
    constants               ai_config.py           timeout, defaults, system prompt
"""

from .ai_client import AIClient
from .ai_config import AiAudit
from .ai_manager import AIManager
from .audit_response_parser import AuditResponseParser
from .openrouter_client import OpenRouterClient

__all__ = ["AIManager", "AIClient", "AiAudit", "AuditResponseParser", "OpenRouterClient"]
