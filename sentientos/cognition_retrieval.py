"""Shared lexical normalization for bounded cognition context selection."""
from __future__ import annotations

import re
import unicodedata


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
