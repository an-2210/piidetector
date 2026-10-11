"""ORG to PERSON relabelling, applied where the evidence is structural.

Two sources, both refusing any span with a legal suffix (Ltd, Inc, Corp, ...):

1. Table column headers. An ORG span in a cell whose column header is a person
   field (Name, Employee, Contact, Owner, ...) is a person.
2. Cross-mention. After entity resolution, an ORG span that equals a resolved
   person mention, or is a "First Last" name compatible with exactly one
   identity, is a person. It is linked to that identity. Ambiguous matches are
   left alone.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, List, Optional, Sequence, Set

from src.models.text_block import TextBlock
from src.pii.config import P4Config
from src.pii.contracts import Finding
from src.pii.disambiguate import ORG_SUFFIX
from src.pii.resolve import names_compatible, parse_name

HEADER_SOURCE = "p4:table_header"
IDENTITY_SOURCE = "p4:identity_link"


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _column_header(block: TextBlock, text: str) -> Optional[str]:
    """Header of the column whose cell contains `text`, or None."""
    if block.block_type != "table" or not isinstance(block.content, list) or not block.content:
        return None
    header_row = block.content[0]
    if not isinstance(header_row, list):
        return None
    for row in block.content[1:]:
        if not isinstance(row, list):
            continue
        for column, cell in enumerate(row):
            if text in str(cell) and column < len(header_row):
                return str(header_row[column])
    return None


def force_person_by_header(
    findings: Sequence[Finding],
    blocks: Sequence[TextBlock],
    config: P4Config,
) -> List[Finding]:
    """Relabel ORG spans in person-like table columns to PERSON. Returns a new list."""
    by_id = {b.block_id: b for b in blocks}
    headers = {h.casefold() for h in config.person_column_headers}
    out: List[Finding] = []
    for finding in findings:
        block = by_id.get(finding.block_id)
        if finding.pii_type == "ORG" and block is not None and not ORG_SUFFIX.search(finding.text):
            header = _column_header(block, finding.text)
            if header is not None and header.strip().casefold() in headers:
                finding = replace(
                    finding,
                    pii_type="PERSON",
                    sources=sorted(set(finding.sources) | {HEADER_SOURCE}),
                )
        out.append(finding)
    return out


def relabel_org_by_identity(
    findings: Sequence[Finding],
    identities: Sequence[dict],
) -> List[Finding]:
    """Relabel ORG spans that match exactly one resolved person identity."""
    # Map each identity to its full-name mentions (initial-only names cannot link alone).
    full_names: Dict[str, List] = {}
    exact: Dict[str, Set[str]] = {}
    for identity in identities:
        for mention in identity["mentions"]:
            parsed = parse_name(mention["text"])
            if parsed is None:
                continue
            exact.setdefault(_normalise(mention["text"]), set()).add(identity["identity_id"])
            if not parsed.is_initial_first:
                full_names.setdefault(identity["identity_id"], []).append(parsed)

    out: List[Finding] = []
    for finding in findings:
        if finding.pii_type != "ORG" or ORG_SUFFIX.search(finding.text):
            out.append(finding)
            continue
        exact_ids = exact.get(_normalise(finding.text), set())
        if len(exact_ids) > 1:
            out.append(finding)  # the same text names two identities: do not guess
            continue
        identity_id = next(iter(exact_ids)) if exact_ids else None
        if identity_id is None:
            parsed = parse_name(finding.text)
            if parsed is None or parsed.is_initial_first:
                out.append(finding)
                continue
            matches = {
                ident
                for ident, names in full_names.items()
                if any(names_compatible(parsed, name) for name in names)
            }
            if len(matches) != 1:
                out.append(finding)
                continue
            identity_id = matches.pop()
        out.append(
            replace(
                finding,
                pii_type="PERSON",
                identity_id=identity_id,
                sources=sorted(set(finding.sources) | {IDENTITY_SOURCE}),
            )
        )
    return out
