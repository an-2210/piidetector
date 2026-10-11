"""Entity resolution: link name mentions, emails and EMP IDs into one identity per person.

Linking rules (no merge on a shared surname alone):

1. Two full names merge when the surnames match and the first names match
   (or one is the initial of the other), and any middle initials agree.
   "Michael T. Achebe" and "Michael Achebe" merge; "Michael Achebe" and
   "Mary Achebe" do not.
2. An initial-only name ("M. Achebe") merges only if it is compatible with
   exactly one existing full-name cluster. If it fits two, it stays separate.
3. An email merges with a person when its local part matches the person's
   name (e.g. michael.achebe, m.achebe, machebe), again only if exactly one
   person cluster fits.
4. An email or EMP ID co-occurring in the same block (or the same table row)
   as exactly one person cluster links to that cluster. If one ID would link
   two different clusters, it is left unlinked and reported as a conflict.

Identity IDs are PERSON_1, PERSON_2, ... in a deterministic order (canonical
name, then first mention). They depend only on the input set, not on
iteration order or hashing. Pass all blocks from a run in one call to get
cross-file identities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

_TITLE_WORDS = {"mr", "mrs", "ms", "miss", "dr", "prof"}
_SUFFIX_WORDS = {"jr", "sr", "ii", "iii"}


@dataclass(frozen=True)
class ParsedName:
    """A person name split into normalised parts."""

    tokens: Tuple[str, ...]

    @property
    def surname(self) -> str:
        return self.tokens[-1]

    @property
    def first(self) -> str:
        return self.tokens[0]

    @property
    def middles(self) -> Tuple[str, ...]:
        return self.tokens[1:-1]

    @property
    def is_initial_first(self) -> bool:
        return len(self.first) == 1


def parse_name(text: str) -> Optional[ParsedName]:
    """Normalise a person mention. Returns None if it has fewer than two name parts."""
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
    while words and words[0] in _TITLE_WORDS:
        words.pop(0)
    while words and words[-1] in _SUFFIX_WORDS:
        words.pop()
    if len(words) < 2:
        return None
    return ParsedName(tuple(words))


def _first_compatible(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) == 1 and b.startswith(a):
        return True
    if len(b) == 1 and a.startswith(b):
        return True
    return False


def _middles_compatible(a: ParsedName, b: ParsedName) -> bool:
    return all(
        x[0] == y[0] for x, y in zip(a.middles, b.middles)
    )


def names_compatible(a: ParsedName, b: ParsedName) -> bool:
    """Two name mentions may refer to the same person."""
    return (
        a.surname == b.surname
        and _first_compatible(a.first, b.first)
        and _middles_compatible(a, b)
    )


def email_matches_name(local_part: str, name: ParsedName) -> bool:
    """True when an email local part plausibly belongs to `name`."""
    tokens = [t for t in re.split(r"[^a-z]+", local_part.lower()) if t]
    compact = "".join(tokens)
    sur, first = name.surname, name.first
    if len(first) > 1:
        if compact == first + sur:
            return True
        return first in tokens and sur in tokens
    # Initial-only first name, e.g. "m.achebe" for "M. Achebe".
    return compact == first + sur or (first in tokens and sur in tokens)


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Smaller index becomes the root, so the structure is deterministic.
            if ra < rb:
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb


def _mention_key(f: Finding) -> Tuple:
    return (f.source_file, f.reading_order, f.start, f.end, f.text)


def _scope_of(f: Finding, blocks_by_id: Dict[str, TextBlock]) -> Tuple:
    """Co-occurrence scope: the block, or the table row inside it."""
    row = -1
    block = blocks_by_id.get(f.block_id)
    if block is not None and block.block_type == "table" and isinstance(block.content, list):
        for index, cells in enumerate(block.content):
            if isinstance(cells, list) and any(f.text in str(cell) for cell in cells):
                row = index
                break
    return (f.source_file, f.block_id, row)


def _value_key(f: Finding) -> Tuple[str, str]:
    if f.pii_type == "EMAIL":
        return ("EMAIL", f.text.strip().lower())
    return (f.pii_type, re.sub(r"\s+", "", f.text).upper())


@dataclass
class ResolutionResult:
    """Output of `resolve_identities`."""

    findings: List[Finding]
    identities: List[dict]
    conflicts: List[str] = field(default_factory=list)


def resolve_identities(
    findings: Sequence[Finding],
    evidence: Sequence[Finding],
    blocks: Iterable[TextBlock],
) -> ResolutionResult:
    """Assign `identity_id` to PERSON findings and describe the identities.

    Args:
        findings: Final findings. PERSON entries receive identity_id.
        evidence: EMAIL / EMP_ID findings used as linking evidence. These can
            be the same objects as in `findings`.
        blocks: Blocks from the run, used to find table rows for co-occurrence.

    Returns:
        ResolutionResult. `findings` is in the input order, with identity_id set.
    """
    blocks_by_id = {b.block_id: b for b in blocks}

    persons = sorted(
        (f for f in findings if f.pii_type == "PERSON"), key=_mention_key
    )
    parsed = [parse_name(p.text) for p in persons]

    # Value nodes for emails and EMP IDs, merged across all occurrences.
    values: Dict[Tuple[str, str], List[Finding]] = {}
    for f in sorted(evidence, key=_mention_key):
        if f.pii_type in ("EMAIL", "EMP_ID"):
            values.setdefault(_value_key(f), []).append(f)
    value_keys = sorted(values)

    n = len(persons)
    uf = _UnionFind(n + len(value_keys))
    value_index = {key: n + i for i, key in enumerate(value_keys)}
    conflicts: List[str] = []

    full = [i for i in range(n) if parsed[i] is not None and not parsed[i].is_initial_first]

    # Rule 1: full-name pairs.
    for a_pos, i in enumerate(full):
        for j in full[a_pos + 1 :]:
            if names_compatible(parsed[i], parsed[j]):
                uf.union(i, j)

    # Rule 2: initial-only names, only when exactly one full-name cluster fits.
    for i in range(n):
        if parsed[i] is None or not parsed[i].is_initial_first:
            continue
        roots = {uf.find(j) for j in full if names_compatible(parsed[i], parsed[j])}
        if len(roots) == 1:
            uf.union(i, roots.pop())

    # Rule 3: email local part against person names, when unambiguous.
    for key in value_keys:
        if key[0] != "EMAIL":
            continue
        local = key[1].split("@", 1)[0]
        roots = {
            uf.find(i)
            for i in range(n)
            if parsed[i] is not None and email_matches_name(local, parsed[i])
        }
        if len(roots) == 1:
            uf.union(value_index[key], roots.pop())

    # Rule 4: co-occurrence in the same block or table row with exactly one person cluster.
    scope_persons: Dict[Tuple, Set[int]] = {}
    for i, p in enumerate(persons):
        scope_persons.setdefault(_scope_of(p, blocks_by_id), set()).add(i)

    person_roots = {uf.find(i) for i in range(n)}
    for key in value_keys:
        candidate_roots: Set[int] = set()
        for occurrence in values[key]:
            scope = _scope_of(occurrence, blocks_by_id)
            members = scope_persons.get(scope, set())
            roots = {uf.find(i) for i in members}
            if len(roots) == 1:
                candidate_roots.add(roots.pop())
        # A value already attached to a person (rule 3) counts as evidence too.
        attached = {uf.find(value_index[key])} & person_roots
        candidate_roots |= attached
        if len(candidate_roots) == 1:
            uf.union(value_index[key], candidate_roots.pop())
        elif len(candidate_roots) > 1:
            conflicts.append(
                f"{key[0]} {key[1]} co-occurs with {len(candidate_roots)} different people; left unlinked"
            )

    # Group persons by cluster and number the clusters deterministically.
    clusters: Dict[int, List[int]] = {}
    for i in range(n):
        clusters.setdefault(uf.find(i), []).append(i)

    def canonical(indices: List[int]) -> str:
        names = [persons[i].text.strip() for i in indices]
        return max(names, key=lambda t: (len(parse_name(t).tokens) if parse_name(t) else 0, t))

    ordered = sorted(
        clusters.values(),
        key=lambda idxs: (
            canonical(idxs).casefold(),
            min(_mention_key(persons[i]) for i in idxs),
        ),
    )

    identity_for: Dict[int, str] = {}
    identities: List[dict] = []
    for number, indices in enumerate(ordered, start=1):
        identity_id = f"PERSON_{number}"
        for i in indices:
            identity_for[i] = identity_id
        root = uf.find(indices[0])
        linked_values = sorted(
            {
                f"{key[0]}:{key[1]}"
                for key in value_keys
                if uf.find(value_index[key]) == root
            }
        )
        identities.append(
            {
                "identity_id": identity_id,
                "canonical_name": canonical(indices),
                "mentions": [
                    {
                        "text": persons[i].text,
                        "source_file": persons[i].source_file,
                        "reading_order": persons[i].reading_order,
                        "start": persons[i].start,
                        "end": persons[i].end,
                    }
                    for i in sorted(indices, key=lambda k: _mention_key(persons[k]))
                ],
                "linked_evidence": linked_values,
            }
        )

    person_position = {id(p): i for i, p in enumerate(persons)}
    resolved: List[Finding] = []
    for f in findings:
        if f.pii_type == "PERSON" and id(f) in person_position:
            resolved.append(replace(f, identity_id=identity_for[person_position[id(f)]]))
        else:
            resolved.append(f)

    return ResolutionResult(findings=resolved, identities=identities, conflicts=conflicts)
