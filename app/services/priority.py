"""
Adaptive priority scoring — ranks accepted flashcards by how urgently they
need review.

The score combines recency (how long a card has gone unstudied, relative to
its own SM-2 interval) with mastery (how low its ease factor is).  Higher
means more urgent.

The elapsed-days arithmetic is compiled per dialect: SQLite has `julianday()`
but PostgreSQL does not, and PostgreSQL's `max()` is aggregate-only (no
two-argument scalar form), so neither can be written portably inline.
"""
from sqlalchemy import Float, case, extract, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement, FunctionElement

from app.models.flashcard import Flashcard

# A card is flagged as "needs focus" once its priority passes this threshold.
NEEDS_FOCUS_THRESHOLD = 3.0


class days_since(FunctionElement):  # noqa: N801 — SQL function naming
    """Days elapsed between the given timestamp column and now."""

    type = Float()
    name = "days_since"
    inherit_cache = True


@compiles(days_since)
def _days_since_default(element, compiler, **kw) -> str:
    """PostgreSQL and other dialects: subtract timestamps, convert to days."""
    (column,) = element.clauses
    inner = extract("epoch", func.now() - column) / 86400.0
    # Parenthesised: the result gets divided by the interval further up the
    # expression, and division binds tighter than the subtraction inside.
    return f"({compiler.process(inner, **kw)})"


@compiles(days_since, "sqlite")
def _days_since_sqlite(element, compiler, **kw) -> str:
    """SQLite: julianday() already returns a day-valued number."""
    (column,) = element.clauses
    inner = func.julianday("now") - func.julianday(column)
    return f"({compiler.process(inner, **kw)})"


def priority_score_expr() -> ColumnElement[float]:
    """SQL expression ranking flashcards by review urgency (higher = sooner)."""
    # Clamp the interval to >= 1 so the division is safe. `func.max(1, col)` is
    # the SQLite-only scalar form and does not exist in PostgreSQL.
    safe_interval = case((Flashcard.interval > 1, Flashcard.interval), else_=1)
    recency_factor = days_since(Flashcard.updated_at) / safe_interval
    return recency_factor + (5.0 - Flashcard.ease_factor)
