"""Verbs — agent-facing data window per AR-PAT-1 Rule C.

Story 2-4 ships only the ``ask_router`` verb shim. Story 2-10 adds Hermes
aux routing. Epic 4 adds the action verbs (propose_action / apply_action
etc.). Story 5-1 adds the read-side verbs.

Story 5-1 reframe: list_unread is NOT shipped — depends on a deferred
sync-side is_read capture (see story 5-1 file §schema-reality reframe).
"""

from mailbot_api.verbs.count_emails import count_emails
from mailbot_api.verbs.find_emails import find_emails
from mailbot_api.verbs.get_sender_summary import get_sender_summary
from mailbot_api.verbs.get_thread import get_thread
from mailbot_api.verbs.hydrate_email import hydrate_email, reset_hydration_count
from mailbot_api.verbs.mute_category import mute_category

__all__ = [
    "count_emails",
    "find_emails",
    "get_sender_summary",
    "get_thread",
    "hydrate_email",
    "mute_category",
    "reset_hydration_count",
]
