"""Production signing key helper (upgrade U1, app/core/production_signing.py).

  python scripts/production_key.py new        -> prints a NEW private key. Put it in PRODUCTION_SIGNING_KEY on the server
                                                 (Render environment), never in git. It is printed only to your terminal.
  python scripts/production_key.py public     -> prints {key_id: public key} of the configured key, to paste into the
                                                 Robot Agent's agent.json as "production_public_keys". Public: safe to share.

Rotation: generate a new key with a new PRODUCTION_SIGNING_KEY_ID; move the old public key into PRODUCTION_VERIFY_KEYS
(JSON {key_id: public}) until every job signed with it is finished; add the new public key to each station's agent.json.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import production_signing as ps  # noqa: E402


def main(argv: list[str]) -> int:
    if argv[1:] == ["new"]:
        print(ps.generate_private_key())
        return 0
    if argv[1:] == ["public"]:
        from app.core.config import get_settings
        s = get_settings()
        if not s.production_signing_key:
            print("PRODUCTION_SIGNING_KEY is not set in this environment.", file=sys.stderr)
            return 2
        print(json.dumps({s.production_signing_key_id: ps.public_key_of(s.production_signing_key)}))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
