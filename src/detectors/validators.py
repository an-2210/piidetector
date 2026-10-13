"""Validation algorithms and boundary cleaners for Rule-Based Detectors (P3)."""

from __future__ import annotations

import calendar
import re
from typing import Tuple


def luhn_checksum(number_str: str) -> bool:
    """Validate a numeric string using the Luhn (Mod 10) algorithm.

    Commonly used for credit cards (Visa, MasterCard, Amex, Discover).
    """
    digits = [int(c) for c in number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False

    total = 0
    reversed_digits = digits[::-1]
    for idx, digit in enumerate(reversed_digits):
        if idx % 2 == 1:
            doubled = digit * 2
            total += doubled - 9 if doubled > 9 else doubled
        else:
            total += digit
    return total % 10 == 0


def validate_ssn(ssn_str: str) -> bool:
    """Validate a US Social Security Number string according to SSA rules.

    Format: AAA-GG-SSSS
    Rules:
    - Area (AAA): Cannot be 000, 666, or 900-999.
    - Group (GG): Cannot be 00.
    - Serial (SSSS): Cannot be 0000.
    """
    parts = ssn_str.split("-")
    if len(parts) != 3:
        return False

    area_str, group_str, serial_str = parts
    if not (len(area_str) == 3 and len(group_str) == 2 and len(serial_str) == 4):
        return False

    if not (area_str.isdigit() and group_str.isdigit() and serial_str.isdigit()):
        return False

    area = int(area_str)
    group = int(group_str)
    serial = int(serial_str)

    if area == 0 or area == 666 or 900 <= area <= 999:
        return False
    if group == 0:
        return False
    if serial == 0:
        return False

    return True


def validate_pan(pan_str: str) -> bool:
    """Validate an Indian Permanent Account Number (PAN).

    Structure: 5 uppercase letters, 4 digits, 1 uppercase letter.
    The 4th character represents the status/entity of the holder:
    P (Person/Individual), C (Company), H (HUF), F (Firm), A (AOP),
    T (Trust), B (BOI), L (Local Authority), J (Artificial Juridical Person),
    G (Government).
    """
    if len(pan_str) != 10:
        return False

    if not (pan_str[:5].isalpha() and pan_str[5:9].isdigit() and pan_str[9].isalpha()):
        return False

    pan_upper = pan_str.upper()
    entity_char = pan_upper[3]
    valid_entities = {"P", "C", "H", "F", "A", "T", "B", "L", "J", "G"}
    return entity_char in valid_entities


def validate_tin(tin_str: str) -> bool:
    """Validate a US Taxpayer Identification / Employer Identification Number (EIN/TIN).

    Format: XX-XXXXXXX (9 digits).
    Prefix cannot be 00 and serial cannot be 0000000.
    """
    parts = tin_str.split("-")
    if len(parts) != 2:
        return False

    prefix_str, serial_str = parts
    if not (len(prefix_str) == 2 and len(serial_str) == 7):
        return False

    if not (prefix_str.isdigit() and serial_str.isdigit()):
        return False

    if prefix_str == "00" or serial_str == "0000000":
        return False

    return True


PESEL_WEIGHTS = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)

# PESEL encodes the century in the month: +80 for 1800s, +0 for 1900s, +20 for
# 2000s, +40 for 2100s, +60 for 2200s.
_PESEL_CENTURY = ((80, 1800), (60, 2200), (40, 2100), (20, 2000), (0, 1900))


def validate_pesel_date(pesel: str) -> bool:
    """True when the first six digits are a real date under PESEL's century-month encoding."""
    if len(pesel) != 11 or not pesel.isdigit():
        return False
    yy, mm, dd = int(pesel[0:2]), int(pesel[2:4]), int(pesel[4:6])
    for offset, century in _PESEL_CENTURY:
        month = mm - offset
        if 1 <= month <= 12:
            year = century + yy
            return 1 <= dd <= calendar.monthrange(year, month)[1]
    return False


def validate_pesel_checksum(pesel: str) -> bool:
    """True when the 11th digit matches the PESEL check digit (weights 1-3-7-9)."""
    if len(pesel) != 11 or not pesel.isdigit():
        return False
    total = sum(int(d) * w for d, w in zip(pesel[:10], PESEL_WEIGHTS))
    return (10 - total % 10) % 10 == int(pesel[10])


def validate_phone(raw_str: str) -> bool:
    """Validate extracted phone number string against basic E.164 constraints.

    Rejects strings with fewer than 7 digits or more than 15 digits,
    repeated digit dummies (e.g. 000-000-0000), or dates/ratios.
    """
    digits = [c for c in raw_str if c.isdigit()]
    digit_count = len(digits)

    if digit_count < 7 or digit_count > 15:
        return False

    # Check for all repeated digits (dummy sequence)
    if len(set(digits)) == 1:
        return False

    # Check if string starts with an invalid standalone year or ratio pattern
    clean_stripped = raw_str.strip()
    if clean_stripped.startswith("0000") or clean_stripped.startswith("1900"):
        return False

    return True


def trim_punctuation_offsets(
    text: str, start: int, end: int
) -> Tuple[str, int, int]:
    """Trim surrounding punctuation (parentheses, quotes, trailing periods) from matches.

    Adjusts start and end offsets accordingly to preserve exact match slices.
    """
    matched = text[start:end]
    l_strip = len(matched) - len(matched.lstrip(" \t\r\n'\"(<[{"))
    new_start = start + l_strip

    matched_after_left = text[new_start:end]
    r_strip = len(matched_after_left) - len(matched_after_left.rstrip(" \t\r\n.,;:!?'\")>]}"))
    new_end = end - r_strip

    if new_start >= new_end:
        return "", start, start

    return text[new_start:new_end], new_start, new_end
