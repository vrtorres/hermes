from __future__ import annotations

import json

from hermes.adapters.imap_reader import ImapMailReader
from hermes.config import ConfigurationError, Settings
from hermes.services.message_parser import MessageParser


def main() -> int:
    """Perform an optional real read-only check and print no body or credentials."""
    try:
        settings = Settings.from_env()
        parser = MessageParser(settings.max_body_text_chars)
        reader = ImapMailReader(settings, parser)
        uidvalidity, uids = reader.search_uids(settings.imap_folder, filters=_empty_filters())
        metadata = reader.fetch_metadata(settings.imap_folder, uidvalidity, uids[:5])
    except ConfigurationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    print(
        json.dumps(
            {
                "ok": True,
                "uidvalidity": uidvalidity,
                "messages": [{"uid": item.uid, "size": item.size} for item in metadata],
            }
        )
    )
    return 0


def _empty_filters():
    from hermes.domain.models import SearchFilters

    return SearchFilters()


if __name__ == "__main__":
    raise SystemExit(main())

