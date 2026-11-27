"""Shared lexical normalization for bounded cognition context selection."""
from __future__ import annotations

import re
import unicodedata
from fractions import Fraction
from typing import Any, Mapping


COMPACT_CHAT_SELECTION = "sentientos.ordinary_chat_developmental_history_selection:v4"


def ordinary_chat_history_partition(selection: Mapping[str, Any]) -> tuple[list, list]:
    """Reconstruct ordered available and omitted refs from an ordinary chat selection."""
    if selection.get("schema_version") != COMPACT_CHAT_SELECTION:
        available, omitted = selection.get("available_records"), selection.get("omitted_records")
        if not isinstance(available, list) or not isinstance(omitted, list):
            raise ValueError("ordinary_chat_history_selection_invalid")
        return available, omitted
    hashes = selection.get("omitted_record_sha256")
    selected = selection.get("selected_records")
    if (not isinstance(selected, list) or not isinstance(hashes, list)
            or not selected or len(selected) + len(hashes) > 16
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in hashes)):
        raise ValueError("ordinary_chat_history_selection_invalid")
    omitted = [{"record_id": "devrec-" + value[:24], "record_digest": "sha256:" + value}
               for value in hashes]
    return selected + omitted, omitted


def render_ordinary_chat_integer_examples(task_family_id: str,
        examples: Any) -> str | None:
    """Render validated scored integer rows without replacing their structured source."""
    if (not isinstance(task_family_id, str)
            or not task_family_id.startswith("rootless_integer_affine_transfer_")
            or not isinstance(examples, (list, tuple)) or not examples):
        return None
    rendered = []
    for row in examples:
        if not isinstance(row, Mapping):
            return None
        probe_input = row.get("probe_input")
        observed_answer = row.get("observed_answer")
        evaluator_correct = row.get("evaluator_correct")
        abstained = row.get("abstained")
        if (type(probe_input) is not int or type(evaluator_correct) is not bool
                or type(abstained) is not bool
                or (abstained and observed_answer is not None)
                or (not abstained and type(observed_answer) is not int)):
            return None
        answer = "no answer" if abstained else str(observed_answer)
        outcome = "abstained" if abstained else (
            "correct" if evaluator_correct else "incorrect")
        rendered.append(f"{probe_input} -> {answer} ({outcome})")
    return "; ".join(rendered)


def derive_ordinary_chat_integer_affine_hypothesis(task_family_id: str,
        examples: Any) -> dict[str, Any] | None:
    """Fit a tentative integer-affine relation from complete, correct scored rows.

    This derives only a candidate within a declared hypothesis class. It does
    not establish correctness outside the observed support examples.
    """
    if (not isinstance(task_family_id, str)
            or not task_family_id.startswith("rootless_integer_affine_transfer_")
            or not isinstance(examples, (list, tuple)) or len(examples) < 3):
        return None
    support = []
    for row in examples:
        if (not isinstance(row, Mapping)
                or type(row.get("probe_input")) is not int
                or type(row.get("observed_answer")) is not int
                or row.get("evaluator_correct") is not True
                or row.get("abstained") is not False):
            return None
        support.append({"probe_input": row["probe_input"],
            "observed_answer": row["observed_answer"]})
    inputs = [row["probe_input"] for row in support]
    if len(set(inputs)) < 3 or len(set((row["probe_input"], row["observed_answer"])
            for row in support)) != len(support):
        return None
    first = support[0]
    second = next((row for row in support[1:]
        if row["probe_input"] != first["probe_input"]), None)
    if second is None:
        return None
    slope = Fraction(second["observed_answer"] - first["observed_answer"],
        second["probe_input"] - first["probe_input"])
    intercept = Fraction(first["observed_answer"]) - slope * first["probe_input"]
    if (slope.denominator != 1 or intercept.denominator != 1
            or any(slope * row["probe_input"] + intercept != row["observed_answer"]
                for row in support)):
        return None
    return {
        "multiplier": slope.numerator,
        "offset": intercept.numerator,
        "support_input_range": [min(inputs), max(inputs)],
    }


_QUERY_NEGATION_WORD_PATTERN = re.compile(r"\b(?:no|nor|not)\b")
_QUERY_NEGATION_CONTRACTION_PATTERN = re.compile(
    r"\b(?:ain|aren|can|couldn|didn|doesn|don|hadn|hasn|haven|isn|mustn|"
    r"shouldn|wasn|weren|won|wouldn)['’]t\b")
_QUERY_CANNOT_PATTERN = re.compile(r"\b(?:cannot|can\s+not)\b")
_QUERY_NEGATION_CONTRACTION_FRAGMENTS = frozenset((
    "ain", "aren", "couldn", "didn", "doesn", "don", "hadn", "hasn",
    "haven", "isn", "mustn", "shouldn", "wasn", "weren", "won", "wouldn"))

_QUERY_STOP_WORDS = frozenset((
    "a", "about", "after", "again", "all", "also", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "between", "both",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down", "each",
    "few", "for", "from", "had", "has", "have", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just",
    "learn", "like", "may", "me", "might", "more", "most", "much", "must", "my",
    "now", "of", "off", "on", "once", "only", "or", "other",
    "our", "ours", "out", "over", "same", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "theirs", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "under", "until", "up", "us", "very",
    "was", "we", "were", "what", "when", "where", "whether", "which", "while", "who",
    "whom", "why", "will", "with", "would", "you", "your", "yours"))

_ELLIPTICAL_FOLLOW_UP_CUES = frozenset((
    "again", "else", "next", "same", "there", "then"))

_NONVERB_ING_WORDS = frozenset((
    "anything", "ceiling", "evening", "everything", "morning", "nothing",
    "something"))
_ING_BASES_WITHOUT_FINAL_E = frozenset((
    "bang", "bring", "cling", "fang", "fling", "hang", "ring", "sing",
    "sling", "spring", "sting", "string", "swing", "wring"))
_IRREGULAR_VES_PLURALS = {
    "calves": "calf",
    "halves": "half",
    "knives": "knife",
    "loaves": "loaf",
    "selves": "self",
    "shelves": "shelf",
    "thieves": "thief",
    "wives": "wife",
    "wolves": "wolf",
}


def normalize_cognition_term(token: str) -> str:
    """Normalize common English inflections without external model dependencies."""
    token = unicodedata.normalize("NFC", token.casefold())
    if token in _IRREGULAR_VES_PLURALS:
        return _IRREGULAR_VES_PLURALS[token]
    if token in _NONVERB_ING_WORDS:
        return token
    if len(token) > 5 and token.endswith("ying"):
        token = token[:-4] + "y"
    elif len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
        if len(token) > 3 and token[-1] == token[-2]:
            token = token[:-1]
        elif token.endswith("g") and token not in _ING_BASES_WITHOUT_FINAL_E:
            token += "e"
    elif len(token) > 4 and token.endswith("ied"):
        token = token[:-3] + "y"
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
        if len(token) > 2 and token[-1] == token[-2]:
            token = token[:-1]
        elif token.endswith(("g", "v")):
            token += "e"
    elif len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes", "zes")):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    return token


def cognition_tokens(text: str) -> tuple[str, ...]:
    """Return NFC-normalized Unicode word terms for retrieval selectors."""
    normalized_text = unicodedata.normalize("NFC", text.casefold())
    return tuple(normalize_cognition_term(token)
        for token in re.findall(r"[^\W_]{3,}", normalized_text))


def cognition_negation_terms(text: str) -> frozenset[str]:
    """Normalize explicit negation cues used to retrieve prior decisions."""
    normalized = unicodedata.normalize("NFC", text.casefold())
    terms = set(_QUERY_NEGATION_WORD_PATTERN.findall(normalized))
    if (_QUERY_NEGATION_CONTRACTION_PATTERN.search(normalized)
            or _QUERY_CANNOT_PATTERN.search(normalized)):
        terms.add("not")
    return frozenset(terms)


def cognition_query_terms(text: str) -> set[str]:
    """Return normalized topic terms while preserving explicit query negation."""
    terms: set[str] = set()
    for token in cognition_tokens(text):
        if (token in _QUERY_STOP_WORDS
                or token in _QUERY_NEGATION_CONTRACTION_FRAGMENTS):
            continue
        terms.add(token)
    terms.update(cognition_negation_terms(text))
    return terms


def is_sparse_or_elliptical_cognition_query(text: str) -> bool:
    """Identify short questions whose topic may depend on the prior user turn."""
    terms = cognition_query_terms(text)
    if len(terms) < 2:
        return True
    return (len(terms) <= 2
        and bool(set(cognition_tokens(text)) & _ELLIPTICAL_FOLLOW_UP_CUES))
