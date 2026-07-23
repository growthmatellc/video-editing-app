"""parser.py — markdown bundle → structured emails/SMS/sections.

Parses Growth Mate's canonical email + SMS bundle format into a structured
representation that rule modules can inspect.

The canonical bundle format (from F-1 to F-12 + Alec Project Transform X layout):

    **EMAIL + SMS LAUNCH BUNDLE — <CLIENT> · vN (<TAG>)** *<workshop tag>*
    *<delta description>*

    -----

    ## GHL VARIABLES USED   (optional · UE-6 requires this)
    ...

    -----

    # SEQUENCE 1 — <TITLE> (counts)

    -----

    **EMAIL #N: DESCRIPTION (TIMING)** **Subject:** <subject text>

    <body>

    -----

    **SMS #N (TIMING):** <body>

    -----

    ...

Each email / SMS becomes a `BundleSection` with:
  - section_type: "email" | "sms" | "sequence_header" | "metadata"
  - number: int or None (the #N identifier)
  - sequence: int (which sequence it belongs to · 1-indexed)
  - subject: str or None
  - body: str (lines joined)
  - body_lines: list of (line_no, content) tuples for line-accurate violation reporting
  - opening_line: str (first non-blank line of body, post-subject and post-{{first_name}})
  - timing_label: str (the (TIMING) annotation · e.g., "5 days before · 9 AM local")
  - start_line: int (line in original file where this section starts)
  - end_line: int (line in original file where this section ends)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# Email header may be either:
#   one line: `**EMAIL #N: DESCRIPTION (TIMING)** **Subject:** ...`
#   two lines: `**EMAIL #N: DESCRIPTION (TIMING)**\n**Subject:** ...`
# Match the FIRST line (with EMAIL + description + timing); we look for Subject
# on the same line OR the next line during section assembly.
EMAIL_HEADER_RE = re.compile(
    r"^\*\*EMAIL\s+#(?P<number>[A-Z]?\d+):\s*(?P<description>.+?)(?:\s*\((?P<timing>[^)]+)\))?\*\*\s*(?:\*\*Subject:\*\*\s*(?P<subject>.+?)\s*)?$",
    re.IGNORECASE,
)
SUBJECT_LINE_RE = re.compile(r"^\*\*Subject:\*\*\s*(?P<subject>.+?)\s*$", re.IGNORECASE)
SMS_HEADER_RE = re.compile(
    r"^\*\*SMS\s+#(?P<number>[A-Z]?\d+)\s*(?:\((?P<timing>[^)]+)\))?:\*\*\s*(?P<body_start>.*)$",
    re.IGNORECASE,
)
SEQUENCE_HEADER_RE = re.compile(
    r"^#\s+SEQUENCE\s+(?P<number>\d+)\s*[—–-]\s*(?P<title>.+?)(?:\s*\((?P<counts>[^)]+)\))?\s*$",
    re.IGNORECASE,
)
DIVIDER_RE = re.compile(r"^-{3,}\s*$")
BUNDLE_TITLE_RE = re.compile(r"^\*\*EMAIL\s*\+\s*SMS LAUNCH BUNDLE", re.IGNORECASE)
END_OF_BUNDLE_RE = re.compile(r"^\*\*END OF BUNDLE", re.IGNORECASE)
GHL_VARS_HEADER_RE = re.compile(r"^##\s+GHL VARIABLES USED", re.IGNORECASE)


@dataclass
class BundleSection:
    section_type: str  # "email" | "sms" | "sequence_header" | "metadata" | "variables_block"
    number: Optional[str] = None  # "1", "2", "R1", "B1", "C0", etc.
    sequence: int = 0
    subject: Optional[str] = None
    description: Optional[str] = None
    timing_label: Optional[str] = None
    body: str = ""
    body_lines: List[tuple] = field(default_factory=list)  # (line_no, content)
    opening_line: Optional[str] = None
    start_line: int = 0
    end_line: int = 0

    @property
    def section_id(self) -> str:
        if self.section_type == "email":
            return f"Email #{self.number}"
        elif self.section_type == "sms":
            return f"SMS #{self.number}"
        elif self.section_type == "sequence_header":
            return f"Sequence {self.sequence}"
        else:
            return self.section_type


@dataclass
class ParsedBundle:
    raw_text: str
    raw_lines: List[str]
    bundle_title: Optional[str] = None
    delta_block: Optional[str] = None
    variables_block: Optional[str] = None  # the entire GHL VARIABLES USED block content
    has_variables_block: bool = False
    sections: List[BundleSection] = field(default_factory=list)

    @property
    def emails(self) -> List[BundleSection]:
        return [s for s in self.sections if s.section_type == "email"]

    @property
    def sms_messages(self) -> List[BundleSection]:
        return [s for s in self.sections if s.section_type == "sms"]

    @property
    def all_communication_sections(self) -> List[BundleSection]:
        """Emails + SMS, in order."""
        return [s for s in self.sections if s.section_type in ("email", "sms")]


def parse_bundle(text: str) -> ParsedBundle:
    """Parse a markdown bundle into a ParsedBundle structure.

    Args:
        text: full markdown content of the bundle

    Returns:
        ParsedBundle with sections populated
    """
    raw_lines = text.splitlines()
    bundle = ParsedBundle(raw_text=text, raw_lines=raw_lines)

    current_sequence = 0
    i = 0
    n = len(raw_lines)

    while i < n:
        line = raw_lines[i]
        line_no = i + 1  # 1-indexed for human-readable line numbers

        # Capture bundle title (first line typically)
        if BUNDLE_TITLE_RE.match(line):
            bundle.bundle_title = line.strip()
            # Capture delta block (subsequent italicized lines)
            delta_lines = []
            j = i + 1
            while j < n and raw_lines[j].strip().startswith("*") and not raw_lines[j].strip().startswith("**"):
                delta_lines.append(raw_lines[j])
                j += 1
            if delta_lines:
                bundle.delta_block = "\n".join(delta_lines)
            i = j
            continue

        # Capture GHL Variables block
        if GHL_VARS_HEADER_RE.match(line):
            bundle.has_variables_block = True
            block_start = i
            # Read until next divider
            j = i + 1
            while j < n and not DIVIDER_RE.match(raw_lines[j]):
                j += 1
            bundle.variables_block = "\n".join(raw_lines[block_start:j])
            i = j
            continue

        # Sequence header
        if SEQUENCE_HEADER_RE.match(line):
            m = SEQUENCE_HEADER_RE.match(line)
            current_sequence = int(m.group("number"))
            section = BundleSection(
                section_type="sequence_header",
                number=m.group("number"),
                sequence=current_sequence,
                description=m.group("title"),
                start_line=line_no,
                end_line=line_no,
            )
            bundle.sections.append(section)
            i += 1
            continue

        # Email header
        m = EMAIL_HEADER_RE.match(line)
        if m:
            subject = m.group("subject")
            body_start_index = i + 1
            # If subject wasn't on the header line, check next non-blank line
            if not subject:
                # Scan forward to find **Subject:** line (skip blanks)
                k = i + 1
                while k < n and not raw_lines[k].strip():
                    k += 1
                if k < n:
                    sm = SUBJECT_LINE_RE.match(raw_lines[k])
                    if sm:
                        subject = sm.group("subject")
                        body_start_index = k + 1
            section = BundleSection(
                section_type="email",
                number=m.group("number"),
                sequence=current_sequence,
                description=m.group("description").strip(),
                timing_label=m.group("timing").strip() if m.group("timing") else None,
                subject=subject.strip() if subject else None,
                start_line=line_no,
            )
            # Read body until next divider or end of file
            body_lines = []
            j = body_start_index
            while j < n and not DIVIDER_RE.match(raw_lines[j]) and not BUNDLE_TITLE_RE.match(raw_lines[j]) and not END_OF_BUNDLE_RE.match(raw_lines[j]):
                # stop also at next email/sms header
                if EMAIL_HEADER_RE.match(raw_lines[j]) or SMS_HEADER_RE.match(raw_lines[j]) or SEQUENCE_HEADER_RE.match(raw_lines[j]):
                    break
                body_lines.append((j + 1, raw_lines[j]))
                j += 1
            section.body_lines = body_lines
            section.body = "\n".join([content for _, content in body_lines])
            section.end_line = j
            section.opening_line = _extract_opening_line(body_lines)
            bundle.sections.append(section)
            i = j
            continue

        # SMS header
        m = SMS_HEADER_RE.match(line)
        if m:
            section = BundleSection(
                section_type="sms",
                number=m.group("number"),
                sequence=current_sequence,
                timing_label=m.group("timing").strip() if m.group("timing") else None,
                start_line=line_no,
            )
            body_start = m.group("body_start") or ""
            body_lines = []
            if body_start.strip():
                body_lines.append((line_no, body_start.strip()))
            j = i + 1
            while j < n and not DIVIDER_RE.match(raw_lines[j]) and not BUNDLE_TITLE_RE.match(raw_lines[j]) and not END_OF_BUNDLE_RE.match(raw_lines[j]):
                if EMAIL_HEADER_RE.match(raw_lines[j]) or SMS_HEADER_RE.match(raw_lines[j]) or SEQUENCE_HEADER_RE.match(raw_lines[j]):
                    break
                body_lines.append((j + 1, raw_lines[j]))
                j += 1
            section.body_lines = body_lines
            section.body = "\n".join([content for _, content in body_lines])
            section.end_line = j
            section.opening_line = _extract_opening_line(body_lines)
            bundle.sections.append(section)
            i = j
            continue

        i += 1

    return bundle


def _extract_opening_line(body_lines: list) -> Optional[str]:
    """Extract the substantive opening line of an email body.

    Skips:
      - Empty lines
      - Bare {{contact.first_name}}, salutations (these are name salutations, not openers)
      - Lines that are ONLY a contact-name placeholder

    Returns the first line that contains actual content meant to engage the reader.
    """
    for line_no, content in body_lines:
        stripped = content.strip()
        if not stripped:
            continue
        # Skip bare name salutations like "{{contact.first_name}},"
        if re.fullmatch(r"\{\{contact\.first_name\}\}\s*,\s*", stripped):
            continue
        # Skip lines that are ONLY {{name}} prefix on a paragraph (like "{{contact.first_name}}, X days from..."
        # · we want THIS line because the "X days from..." part is the opener content
        return stripped
    return None


def parse_file(file_path: str) -> ParsedBundle:
    """Convenience wrapper · read file and parse."""
    with open(file_path, "r", encoding="utf-8") as f:
        return parse_bundle(f.read())
