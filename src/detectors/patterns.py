"""Regex definitions and compiled patterns for Rule-Based Detectors (P3)."""

from __future__ import annotations

import re

# ==============================================================================
# 1. Institutional Identifiers
# ==============================================================================
# EMP: EMP- followed by 4 to 6 digits (e.g. EMP-40123)
EMP_PATTERN = re.compile(r"\bEMP-\d{4,6}\b")

# DIR: DIR- followed by 4 to 8 alphanumeric characters or digits (e.g. DIR-4012, DIR-A109B)
# Negative lookahead ensures common words like DIRECTION or DIRECTOR are not matched.
DIR_PATTERN = re.compile(r"\bDIR-(?!(?:ECTION|ECTOR)\b)[A-Z0-9]{4,8}\b")

# MER-IN: Meridian India vendor/entity code (e.g. MER-IN-1002, MER-IN-94012)
MER_IN_PATTERN = re.compile(r"\bMER-IN-[A-Z0-9]{3,8}\b")

# MER-PH: Meridian Philippines vendor/entity code (e.g. MER-PH-2001, MER-PH-49012)
MER_PH_PATTERN = re.compile(r"\bMER-PH-[A-Z0-9]{3,8}\b")


# ==============================================================================
# 2. Email Addresses
# ==============================================================================
# RFC standard regex pattern for corporate & standard email addresses
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"
)


# ==============================================================================
# 3. Global Phone Numbers
# ==============================================================================
# International E.164 and localized telephone formats
# Supports +, country codes, optional parentheses, spaces/hyphens/dots
PHONE_PATTERN = re.compile(
    r"(?:(?:\+|00)\b[1-9]\d{0,2}[-.\s]?)?"        # International prefix e.g. +1, +44, +91
    r"(?:\(?\d{2,5}\)?[-.\s]?)?"                  # Area code e.g. (800), 020
    r"\d{3,5}[-.\s]?"                             # Exchange e.g. 555, 98765
    r"\d{4,5}\b"                                  # Subscriber number e.g. 0199, 43210
)


# Phone cue just before a number: required for bare 11-digit numbers.
PHONE_CUE_PATTERN = re.compile(
    r"(?i)(?:\btel(?:ephone)?\b\.?|\bphone\b|\bmobile\b|\bmob\b\.?|\bcell\b|\bfax\b|"
    r"\bwhatsapp\b|\bcall\b|\+)\s*(?:no\.?|number|#)?\s*[:\-]?\s*$"
)


# ==============================================================================
# 4. Sensitive Identifiers
# ==============================================================================
# US SSN: 3 digits - 2 digits - 4 digits
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Indian PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# US Taxpayer Identification / Employer Identification Number (EIN/TIN): XX-XXXXXXX
TIN_PATTERN = re.compile(r"\b\d{2}-\d{7}\b")

# Polish PESEL: 11 digits (YYMMDD + serial + check digit), validated in validators.py
PESEL_PATTERN = re.compile(r"\b\d{11}\b")
# "PESEL" label shortly before the number (context boost)
PESEL_CONTEXT_PATTERN = re.compile(r"(?i)\bPESEL\b(?:\s*(?:no\.?|nr\.?|number|#))?\s*[:\-]?\s*$")

# PSEF: Professional/Public Service Entity Filing identifier (e.g. PSEF-9901-X)
PSEF_PATTERN = re.compile(r"\bPSEF-[A-Z0-9-]{4,12}\b")

# Passport Number: Contextually labeled or prefixed passport pattern
PASSPORT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:passport(?:\s+(?:number|no\.?|#|id))?\s*[:\-]?\s*)([A-Z0-9]{8,9})\b"
)
PASSPORT_STANDALONE_PATTERN = re.compile(r"\b[A-Z]{1,2}[0-9]{7,8}\b")


# ==============================================================================
# 5. Financial & Account-Related Identifiers
# ==============================================================================
# Credit/Debit Card: 13 to 19 digits formatted with delimiters or contiguous
CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{1,7}"
    r"|\d{4}[-\s]\d{6}[-\s]\d{4,5}"
    r"|\d{13,19})\b"
)

# Account Number ending in last 4 digits (e.g. "Account ending in 4102", "Acct: ****1234")
ACCOUNT_LAST4_PATTERN = re.compile(
    r"(?i)\b(?:account|acct|acc)(?:\s+(?:number|no\.?|#))?"
    r"(?:\s+(?:ending\s+in|ending|last\s*4))?\s*[:\-]?\s*"
    r"(?:(?:\*|x|X){4,}\s*|\b)(\d{4})\b"
)

ACCOUNT_ENDING_PATTERN = re.compile(
    r"(?i)\b(?:ending\s+in(?:\s+last\s*4)?|last\s*4\s*digits)\s*[:\-]?\s*(\d{4})\b"
)

ACCOUNT_PREFIX_PATTERN = re.compile(
    r"\b(?:ACC|ACCT|AC)-[A-Z0-9]{5,12}\b"
)

# Date of Birth (DOB): Strictly context-anchored date pattern
DOB_PATTERN = re.compile(
    r"(?i)\b(?:dob|d\.o\.b\.|date\s+of\s+birth|birth\s*date|born\s+(?:on)?)\s*[:\-]?\s*"
    r"((?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2})"
    r"|(?:\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
    r"|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})"
    r"|(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}))\b"
)

# Physical Street Address
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-zA-Z0-9.\s]{2,30}?\s+"
    r"(?:Street|St\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Road|Rd\.?|Lane|Ln\.?|"
    r"Drive|Dr\.?|Court|Ct\.?|Way|Place|Pl\.?|Plaza|Plz\.?|Parkway|Pkwy\.?|Highway|Hwy\.?)"
    r"(?:,\s*(?:Suite|Ste\.?|Apt\.?|Unit|Floor|Fl\.?|Building|Bldg\.?)\s*[A-Za-z0-9#-]+)?"
    r"(?:,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?\b"
)


# ==============================================================================
# 6. False-Positive Indicators
# ==============================================================================
# Internal non-sensitive reference prefixes to suppress. Matches the whole reference
# (e.g. RSK-2024-0031, not just RSK-2024), so digits inside it can be suppressed.
# Mirrors the reference entries of IGNORE_PATTERNS in src/pii/contracts.py (P4),
# which P3 cannot import because that module is not on this branch. Keep in sync.
INTERNAL_REF_PATTERN = re.compile(
    r"\b(?:RSK|ISS|INC)-[A-Z0-9][A-Z0-9-]*\b|\bGRP-POL-[\w.-]+\b"
)

# Currency and USD amounts (to prevent confusing with account / card numbers)
CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?i)(?:\$\s*\d+(?:,\d{3})*(?:\.\d+)?|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|INR)\b)"
)

# Financial ratios and percentages
RATIO_PERCENT_PATTERN = re.compile(
    r"\b(?:\d+(?:\.\d+)?%|\d+(?:\.\d+)?x|\d+:\d+)\b"
)

# Policy and governance dates that should NOT be detected as DOB
POLICY_DATE_KEYWORDS = re.compile(
    r"(?i)\b(?:effective\s*date|policy\s*date|approved\s*on|review\s*date|"
    r"version\s*date|publication\s*date|expiry\s*date|revised\s*on)\b"
)
