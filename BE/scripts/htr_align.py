"""The E2a matcher now lives in the product (`app/services/stroke_ai/htr_align.py`, V2 Phase E2b); the benchmark
scripts import it from here."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.stroke_ai.htr_align import *          # noqa: E402,F401,F403
from app.services.stroke_ai.htr_align import match, units_of, letters, placeholder, words_of   # noqa: E402,F401
