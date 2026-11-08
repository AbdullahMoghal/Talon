"""Indicator patterns: used to validate what the Extractor agent returns (and by FakeLLM to extract).

Validation is the precision guard: a model-extracted indicator is kept only if its value
appears in the scammer's text and has the right format for its kind. False indicators
would cause wrongful blocks, so anything that fails is dropped and logged.
"""

from __future__ import annotations

import re

from .store import normalize_value

PATTERNS: dict[str, re.Pattern] = {
    "url": re.compile(r"\b(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?", re.I),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"),
    "phone": re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "wallet": re.compile(
        r"\b(?:0x[a-fA-F0-9]{40}|bc1[a-z0-9]{25,59}|[13][a-km-zA-HJ-NP-Z1-9]{25,34}|T[a-km-zA-HJ-NP-Z1-9]{33})\b"
    ),
    "payment_handle": re.compile(r"(?<![\w$])\$[A-Za-z][A-Za-z0-9_-]{2,20}\b|(?<![\w@.])@[A-Za-z][A-Za-z0-9_-]{2,30}\b(?!\.)"),
    "account": re.compile(r"\b(?:routing|acct|account)(?:\s*(?:number|no\.?|#))?\D{0,12}(\d{6,17})\b", re.I),
    "remote_access_id": re.compile(
        r"\b(?:anydesk|teamviewer|session(?:\s*id)?|support\s*code)\D{0,15}(\d(?:[\d ]{5,12})\d)\b", re.I
    ),
    "giftcard_ask": re.compile(
        r"[^.!?\n]*\b(?:gift\s?cards?|google\s?play|apple\s?(?:gift\s?)?card|itunes|steam\s?card)\b[^.!?\n]*", re.I
    ),
}

TRAILING = ".,;:!?)\"'"

# Brand names worth matching by pattern. The taxonomy lists brand types ("toll agencies"); a model knows
# names, but pattern matching needs a list. Used by FakeLLM and for intel from a scammer's first text.
KNOWN_BRANDS = ["E-ZPass", "SunPass", "TxTag", "NTTA", "FasTrak", "USPS", "UPS", "FedEx", "DHL", "Amazon", "Walmart",
                "Target", "Costco", "Medicare", "IRS", "Social Security", "DMV", "T-Mobile", "AT&T", "Verizon", "Apple",
                "Microsoft", "Netflix", "Geek Squad", "Norton", "McAfee", "Chase", "Wells Fargo", "Bank of America",
                "Citi", "Capital One", "PayPal", "Coinbase", "Binance", "Red Cross"]


def _clean(kind: str, value: str) -> str:
    value = value.strip()
    if kind in ("url", "email", "payment_handle"):
        value = value.rstrip(TRAILING)
    return value


def regex_extract(text: str, brands: list[str] | None = None) -> list[dict]:
    """Pattern-based extraction. FakeLLM uses this; the real Extractor uses a model."""
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()
    emails = {m.group(0) for m in PATTERNS["email"].finditer(text)}
    for kind, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            value = _clean(kind, m.group(1) if pattern.groups else m.group(0))
            if kind == "url" and (any(value in e for e in emails) or value.replace(".", "").isdigit()):
                continue
            if kind == "payment_handle" and any(value.lstrip("@") in e for e in emails):
                continue
            key = (kind, normalize_value(value))
            if value and key not in seen:
                seen.add(key)
                found.append({"kind": kind, "value": value, "confidence": 0.9})
    for brand in brands or []:
        if re.search(rf"\b{re.escape(brand)}\b", text, re.I) and ("brand", normalize_value(brand)) not in seen:
            seen.add(("brand", normalize_value(brand)))
            found.append({"kind": "brand", "value": brand, "confidence": 0.8})
    return found


def validate(kind: str, value: str, text: str, allowed_kinds: list[str]) -> str | None:
    """Return a reason to reject this indicator, or None if it's valid."""
    if kind not in allowed_kinds:
        return f"unknown indicator kind {kind!r}"
    if not value or not value.strip():
        return "empty value"
    if normalize_value(value) not in normalize_value(text):
        return "value does not appear in the message"
    pattern = PATTERNS.get(kind)
    if pattern and kind not in ("giftcard_ask",):
        matches = [_clean(kind, m.group(1) if pattern.groups else m.group(0)) for m in pattern.finditer(value)]
        if not any(normalize_value(m) == normalize_value(value) for m in matches):
            return f"value is not a valid {kind}"
    return None


def message_intel(text: str, brand: str | None = None) -> tuple[list[str], list[str]]:
    """Brands and intel ("kind: value") straight from one scam text, for the scammer catalog.

    The first text usually says who the scammer pretends to be and where to pay or click, so this runs on
    every scam text Talon sees, including ones it warns about or blocks without ever replying.
    brand: what triage said the text claims to be from; kept only if it appears in the text.
    """
    found = regex_extract(text, KNOWN_BRANDS)
    brands = [i["value"] for i in found if i["kind"] == "brand"]
    if brand and brand.strip() and normalize_value(brand) in normalize_value(text):
        if normalize_value(brand) not in {normalize_value(b) for b in brands}:
            brands.insert(0, brand.strip())
    intel = [f"brand: {b}" for b in brands] + [f"{i['kind']}: {i['value']}" for i in found if i["kind"] != "brand"]
    return brands, intel
