from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

try:
    import pymupdf as fitz  # PyMuPDF preferred import
except ImportError:
    import fitz  # backward-compatible fallback


# Canonical syllabus concepts. These are intentionally phrased generically so the
# viewer is not tied to one institution, course, textbook, or programming language.
# A topic can use both literal keywords and regex-style patterns for common wording.
TOPICS: Dict[str, dict] = {
    "course_overview": {
        "label": "Course Overview & Prerequisites",
        "keywords": [
            "course overview", "course description", "catalog description", "course information", "course objective",
            "prerequisite", "prerequisites", "co-requisite", "corequisite", "recommended background",
            "prior knowledge", "course title", "course number", "credit hours", "credits","expected background"
        ],
        "patterns": [
            r"\bprerequisites?\b",
            r"\brecommended (?:background|preparation|knowledge)\b",
        ],
    },
    "learning_objectives": {
        "label": "Learning Objectives & Outcomes",
        "keywords": [
            "learning objectives", "course objectives", "learning outcomes", "course outcomes",
            "student learning outcomes", "objectives", "outcomes", "goals", "competencies",
            "skills you will learn", "what you will learn", "by the end of this course"
        ],
        "patterns": [
            r"students? will be able to",
            r"upon (?:successful )?completion",
            r"by the end of (?:this|the) course",
            r"learners? will (?:be able to|demonstrate|understand|apply|analyze|create)",
        ],
    },
    "course_materials": {
        "label": "Textbooks & Course Materials",
        "keywords": [
            "textbook", "textbooks", "required text", "required textbook", "recommended text",
            "course materials", "required materials", "reading materials", "readings", "book",
            "books", "isbn", "edition", "open educational resource", "oer", "reference material",
            "supplemental materials", "supplementary materials"
        ],
        "patterns": [
            r"\bisbn(?:-1[03])?\b",
            r"\b\d+(?:st|nd|rd|th) edition\b",
            r"(?:required|recommended) (?:text|book|reading|materials?)",
        ],
    },
    "technology": {
        "label": "Technology, Programming Languages & Software",
        "keywords": [
            "required software", "software requirements", "software", "technology requirements",
            "technology", "technical requirements", "computer requirements", "system requirements",
            "programming language", "coding language", "development environment", "toolchain",
            "ide", "compiler", "interpreter", "runtime", "sdk", "jdk", "environment setup",
            "installation", "install", "platform", "browser requirements", "laptop requirements",
            # Common languages/tools are examples, not assumptions about the course.
            "python", "java", "javascript", "typescript", "c++", "c#", "visual basic", "ruby",
            "swift", "kotlin", "rust", "golang", "matlab", "r studio", "rstudio", "sql",
            "html", "css", "php", "scala", "julia", "bash", "shell", "powershell",
            "eclipse", "intellij", "visual studio", "vs code", "vscode", "jupyter", "git", "github"
        ],
        "patterns": [
            r"\b(?:python|java|javascript|typescript|ruby|swift|kotlin|rust|scala|julia|matlab|sql)\b",
            r"\bc\+\+\b",
            r"\bc#\b",
            r"\b(?:ide|compiler|interpreter|sdk|jdk|runtime)\b",
        ],
    },
    "grading": {
        "label": "Grading Scheme & Assessment Weights",
        "keywords": [
            "grading", "grading scheme", "grade distribution", "grade scale", "assessment",
            "assessments", "evaluation", "projects", "project", "assignments", "assignment",
            "homework", "labs", "quizzes", "quiz", "midterm", "exam", "final exam",
            "percentage", "percent", "%", "points", "weight", "weights", "weighted"
        ],
        "patterns": [
            r"\b\d+(?:\.\d+)?\s*%",
            r"\b(?:points?|pts?)\b",
        ],
    },
    "late_submission": {
        "label": "Late Work, Deadlines & Submission Rules",
        "keywords": [
            "late submission", "late submissions", "late work", "late assignment", "late assignments",
            "deadline", "deadlines", "due date", "due dates", "submitted late", "after the deadline",
            "late penalty", "late penalties", "deduction", "extension", "extensions", "grace period",
            "no submissions", "cutoff", "submission window", "missed deadline"
        ],
        "patterns": [
            r"submitted? .* after .* due",
            r"after .* deadline",
            r"late .* (?:penalty|deduction|credit)",
            r"\bdue (?:on|by|date)\b",
        ],
    },
    "academic_integrity": {
        "label": "Academic Integrity & Collaboration Rules",
        "keywords": [
            "academic integrity", "academic honesty", "academic dishonesty", "honor code",
            "plagiarism", "collaboration", "collaborate", "copied", "copying", "cheating",
            "original work", "unauthorized assistance", "violation", "integrity", "citation",
            "attribution", "generative ai", "artificial intelligence", "chatgpt", "ai policy"
        ],
        "patterns": [
            r"\b(?:plagiaris[em]|cheating|collaboration)\b",
            r"\b(?:generative ai|artificial intelligence|chatgpt)\b",
        ],
    },
    "attendance": {
        "label": "Attendance & Participation Policy",
        "keywords": [
            "attendance", "participation", "absence", "absences", "present", "class participation",
            "lecture attendance", "lab attendance", "mandatory attendance", "required attendance",
            "participation grade", "clicker", "iclicker"
        ],
        "patterns": [r"\babsen(?:ce|ces|t)\b"],
    },
    "schedule": {
        "label": "Course Schedule & Important Dates",
        "keywords": [
            "course schedule", "class schedule", "weekly schedule", "tentative schedule", "calendar",
            "course calendar", "important dates", "key dates", "weekly topics", "week 1", "week 2",
            "exam date", "project due", "assignment due", "semester schedule",
            # Common schedule-table headers. These are weak individually but strong in combination.
            "date | topic", "week | topic", "date | subject", "week | subject",
            "topic | reading", "topic | readings", "topic | assignment", "topic | assignments",
            "date | lecture", "week | module", "class date", "reading assignment"
        ],
        # "patterns": [
        #     r"\bweek\s*\d+\b",
        #     r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        #     r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b",
        #     r"\b(?:date|week)\s*\|\s*(?:topic|subject|module|lecture)\b",
        #     r"\btopic\s*\|\s*(?:reading|readings|assignment|assignments|chapter)\b",
        # ],

        "patterns": [
            r"\bweek\s*\d+\b",
            r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b",
            r"\b(?:date|week)\s*\|\s*(?:topic|subject|module|lecture)\b",
            r"\btopic\s*\|\s*(?:reading|readings|assignment|assignments|chapter)\b",
        ],
    },
    "support_accommodations": {
        "label": "Student Support & Accommodations",
        "keywords": [
            "accommodations", "accommodation", "accessibility", "disability", "disabilities",
            "student support", "academic support", "tutoring", "learning center",
            "counseling", "student services", "accessibility services", "disability services"
        ],
        "patterns": [
            r"students? with disabilities",
            r"reasonable accommodations?",
        ],
    },
}


@dataclass
class TextBlock:
    page: int
    block_index: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    source_type: str = "text"  # "text" or "table"

    def bbox(self) -> List[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class TopicMatch:
    topic_id: str
    topic_label: str
    page: int
    bbox: List[float]
    anchor_text: str
    context_text: str
    score: float
    confidence: float
    source_type: str = "text"


@dataclass
class ProcessedDocument:
    document_id: str
    filename: str
    page_sizes: List[Tuple[float, float]]
    rendered_pages: List[str]
    topic_matches: List[dict]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _score_block(text: str, spec: dict) -> float:
    t = _norm(text)
    if not t:
        return 0.0

    score = 0.0
    keyword_hits = 0

    for kw in spec.get("keywords", []):
        k = _norm(kw)

        if not k:
            continue

        # Multi-word phrases can be matched directly.
        # Single-word keywords should match whole words only.
        if " " in k:
            matched = k in t
        else:
            matched = bool(
                re.search(
                    rf"(?<!\w){re.escape(k)}(?!\w)",
                    t,
                    flags=re.IGNORECASE,
                )
            )

        if matched:
            keyword_hits += 1

            # Longer phrases are stronger evidence than isolated terms.
            score += (
                3.0
                if len(k.split()) >= 3
                else (2.0 if " " in k else 1.0)
            )

    for pattern in spec.get("patterns", []):
        if re.search(pattern, t, flags=re.IGNORECASE):
            score += 2.5

    # Short blocks with topic evidence are likely headings, so boost them.
    words = t.split()
    if len(words) <= 14 and score > 0:
        score *= 1.45

    # Multiple independent clues in one block are stronger than a single generic word.
    if keyword_hits >= 2:
        score *= 1.15

    return score


def _confidence(score: float) -> float:
    # Conservative heuristic for an MVP. Higher scores require multiple/stronger clues.
    return round(min(0.99, score / (score + 4.0)), 3) if score > 0 else 0.0


def _clean_cell(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _table_to_text(rows: List[List[object]]) -> str:
    """Convert a detected table to a compact, LLM/search-friendly representation.

    Pipes deliberately preserve the column relationships. For example:
        Week | Topic | Reading
        1 | Introduction | Chapter 1
    This makes schedule-style tables detectable without requiring a fixed layout.
    """
    rendered_rows = []
    for row in rows or []:
        cells = [_clean_cell(cell) for cell in row]
        if not any(cells):
            continue
        rendered_rows.append(" | ".join(cells))
    return "\n".join(rendered_rows).strip()


def _bbox_iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = [float(v) for v in a]
    bx0, by0, bx1, by1 = [float(v) for v in b]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _usable_table(rows: List[List[object]]) -> bool:
    cleaned = [[_clean_cell(cell) for cell in row] for row in (rows or [])]
    nonempty_rows = [row for row in cleaned if any(row)]
    max_cols = max((len(row) for row in nonempty_rows), default=0)
    return len(nonempty_rows) >= 2 and max_cols >= 2


def _extract_tables_from_page(page, page_idx: int, start_index: int) -> List[TextBlock]:
    """Detect bordered and borderless tables on a page.

    PyMuPDF's normal line strategy is excellent for grid tables. A second text-based
    pass catches common syllabus tables that are just aligned columns with no borders.
    Overlapping results are de-duplicated, preferring the line-based table.
    """
    candidates = []

    for strategy in ("lines", "text"):
        try:
            finder = page.find_tables(strategy=strategy)
            tables = getattr(finder, "tables", []) or []
        except Exception:
            continue

        for table in tables:
            try:
                rows = table.extract()
                if not _usable_table(rows):
                    continue
                table_text = _table_to_text(rows)
            except Exception:
                continue
            if not table_text:
                continue

            bbox = getattr(table, "bbox", None)
            if not bbox or len(bbox) != 4:
                continue
            bbox = tuple(float(v) for v in bbox)

            # The text strategy often rediscovers a bordered table as a slightly larger
            # region. Keep the line-based result when the regions substantially overlap.
            if any(_bbox_iou(bbox, prior[0]) >= 0.60 for prior in candidates):
                continue

            candidates.append((bbox, table_text, strategy))

    table_blocks: List[TextBlock] = []
    next_index = start_index
    for bbox, table_text, strategy in candidates:
        x0, y0, x1, y1 = bbox
        table_blocks.append(
            TextBlock(
                page=page_idx,
                block_index=next_index,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                text=table_text,
                source_type="table",
            )
        )
        next_index += 1

    return table_blocks

def extract_blocks(pdf_path: Path) -> Tuple[List[TextBlock], List[Tuple[float, float]]]:
    """Extract both ordinary text blocks and structured tables from every PDF page."""
    doc = fitz.open(pdf_path)
    blocks: List[TextBlock] = []
    sizes: List[Tuple[float, float]] = []

    for page_idx, page in enumerate(doc):
        sizes.append((float(page.rect.width), float(page.rect.height)))

        raw_blocks = page.get_text("blocks", sort=True)
        page_blocks: List[TextBlock] = []
        for bi, b in enumerate(raw_blocks):
            x0, y0, x1, y1, text = b[:5]
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            page_blocks.append(
                TextBlock(page_idx, bi, x0, y0, x1, y1, text, source_type="text")
            )

        # PyMuPDF's normal text blocks often flatten or fragment tables. Add a second,
        # structured representation of each detected table so rows/columns remain legible.
        table_blocks = _extract_tables_from_page(page, page_idx, start_index=len(raw_blocks) + 1000)
        page_blocks.extend(table_blocks)

        # Keep a stable visual reading order for nearby-context construction.
        page_blocks.sort(key=lambda b: (b.y0, b.x0, 0 if b.source_type == "text" else 1))
        blocks.extend(page_blocks)

    doc.close()
    return blocks, sizes

def _context_for(blocks: List[TextBlock], chosen: TextBlock, radius: int = 3) -> str:
    same_page = sorted(
        [b for b in blocks if b.page == chosen.page],
        key=lambda b: (b.y0, b.x0, 0 if b.source_type == "text" else 1),
    )
    try:
        pos = next(
            i for i, b in enumerate(same_page)
            if b.block_index == chosen.block_index and b.source_type == chosen.source_type
        )
    except StopIteration:
        return chosen.text

    # A table is already a self-contained multi-row structure. Give it a little nearby
    # text (usually the heading / explanatory sentence), but always preserve the full table.
    if chosen.source_type == "table":
        nearby = []
        if pos > 0:
            nearby.append(same_page[pos - 1].text)
        nearby.append(chosen.text)
        if pos + 1 < len(same_page):
            next_block = same_page[pos + 1]
            # Avoid appending another huge table to the prompt.
            if next_block.source_type != "table":
                nearby.append(next_block.text)
        return "\n".join(nearby)

    # lo = max(0, pos - radius)
    # hi = min(len(same_page), pos + radius + 1)

    lo = pos
    hi = min(len(same_page),pos + radius + 1,)

    return "\n".join(b.text for b in same_page[lo:hi])


def _looks_like_schedule_table(text: str) -> bool:
    t = _norm(text)
    cues = sum(
        1
        for cue in ("week", "date", "topic", "reading", "chapter", "assignment", "module", "lecture", "due")
        if cue in t
    )
    has_calendar_signal = bool(
        re.search(r"\bweek\s*\d+\b", t)
        or re.search(r"\b(?:monday|tuesday|wednesday|thursday|friday)\b", t)
        or re.search(r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}\b", t)
        or "calendar" in t
        or "schedule" in t
    )
    # Tables with several column semantics (e.g. Date/Topic/Reading) are schedules
    # even if their rows use bare dates/numbers rather than the word "week".
    return has_calendar_signal or cues >= 3

def _explicit_late_policy(text: str) -> bool:
    """
    True when the text actually describes a late-work policy,
    rather than merely containing a due date inside a schedule.
    """
    t = _norm(text)

    strong_cues = (
        "late work",
        "late submission",
        "late submissions",
        "submitted late",
        "late penalty",
        "late penalties",
        "grace period",
        "no submissions",
        "after the deadline",
        "after the due date",
        "missed deadline",
        "extension policy",
    )

    if any(cue in t for cue in strong_cues):
        return True

    if re.search(
        r"\b(?:late|after the deadline|after the due date).{0,80}"
        r"(?:penalty|deduction|points?|percent|%|credit|accepted|submission)",
        t,
    ):
        return True

    return False


def _explicit_grading_policy(text: str) -> bool:
    """
    Distinguish an actual grading/assessment section from a schedule
    that merely mentions assignments, quizzes, or exams.
    """
    t = _norm(text)

    strong_cues = (
        "grading scheme",
        "grading policy",
        "grade scale",
        "grade distribution",
        "assessment weights",
        "assessment weight",
        "final grade",
        "course grade",
        "percentage of grade",
    )

    if any(cue in t for cue in strong_cues):
        return True

    # Percentages are good evidence when paired with assessment language.
    if re.search(r"\b\d+(?:\.\d+)?\s*%", t):
        if any(
            word in t
            for word in (
                "grade",
                "grading",
                "project",
                "assignment",
                "homework",
                "quiz",
                "exam",
                "midterm",
                "final",
                "lab",
                "participation",
            )
        ):
            return True

    return False


def _adjusted_topic_score(
    topic_id: str,
    block: TextBlock,
    blocks: List[TextBlock],
    spec: dict,
) -> float:
    """
    Score a block for a topic while using nearby context and
    preventing schedule tables from being misclassified.
    """
    base_score = _score_block(block.text, spec)

    if topic_id == "course_overview":
      t = _norm(block.text)

      if (
        "expected background" in t
        or "prerequisite" in t
        or "prerequisites" in t
        or "prior knowledge" in t
        or "recommended background" in t
      ):
          
        base_score *= 1.25

    if base_score <= 0:
        return 0.0

    # -------------------------------------------------------
    # Important protection:
    # schedule tables naturally contain words such as
    # assignment, exam, due, deadline, etc.
    # Do not let those words steal the table from Schedule.
    # -------------------------------------------------------
    if block.source_type == "table" and _looks_like_schedule_table(block.text):

        if topic_id == "schedule":
            return base_score * 1.75

        if topic_id == "late_submission":
            if not _explicit_late_policy(block.text):
                return 0.0

        if topic_id == "grading":
            if not _explicit_grading_policy(block.text):
                return 0.0

        # Other categories should generally not anchor to a schedule table.
        if topic_id in {
            "course_overview",
            "learning_objectives",
            "course_materials",
            "technology",
            "academic_integrity",
            "attendance",
            "support_accommodations",
        }:
            return 0.0

    # -------------------------------------------------------
    # Examine nearby content.
    # A heading may contain only "Learning Objectives",
    # while the actual objective bullets live below it.
    # -------------------------------------------------------
    context = _context_for(blocks, block, radius=3)

    context_score = _score_block(context, spec)

    # Anchor evidence remains most important.
    # Nearby context only strengthens it.
    combined = base_score + (context_score * 0.35)

    # Short text blocks are often headings.
    word_count = len(_norm(block.text).split())

    if word_count <= 10 and base_score > 0:
        combined *= 1.20

    return combined

# def detect_topics(blocks: List[TextBlock]) -> List[TopicMatch]:
#     matches: List[TopicMatch] = []

#     for topic_id, spec in TOPICS.items():
#         ranked = []
#         for block in blocks:
#             score = _score_block(block.text, spec)
#             if score > 0:
#                 # Tables with multiple schedule cues are especially meaningful in syllabi.
#                 # Do not globally favor tables; only add a modest bonus for the schedule topic.
#                 if topic_id == "schedule" and block.source_type == "table" and _looks_like_schedule_table(block.text):
#                     score *= 1.50
#                 ranked.append((score, block))

#         if not ranked:
#             continue

#         ranked.sort(key=lambda x: (-x[0], x[1].page, x[1].y0))
#         score, best = ranked[0]

#         context_text = _context_for(blocks, best)
#         if topic_id == "schedule":
#             # A weekly schedule often spans multiple PDF pages. Feed all schedule-like
#             # tables to the agents as one conceptual section, while anchoring the UI to
#             # the strongest matching table / heading.
#             schedule_tables = [
#                 block for _, block in ranked
#                 if block.source_type == "table" and _looks_like_schedule_table(block.text)
#             ]
#             # De-duplicate the same table when different extraction strategies produced
#             # near-identical text, then retain document order.
#             unique_tables = []
#             seen = set()
#             for table_block in sorted(schedule_tables, key=lambda b: (b.page, b.y0, b.x0)):
#                 key = (table_block.page, _norm(table_block.text)[:240])
#                 if key in seen:
#                     continue
#                 seen.add(key)
#                 unique_tables.append(table_block)

#             if unique_tables:
#                 pieces = [
#                     f"[Schedule table - PDF page {tb.page + 1}]\n{tb.text}"
#                     for tb in unique_tables
#                 ]
#                 combined = "\n\n".join(pieces)
#                 # Prevent an unusually large semester calendar from overwhelming a local
#                 # model context window while keeping ordinary 14-16 week schedules intact.
#                 context_text = combined[:16000]

#         matches.append(
#             TopicMatch(
#                 topic_id=topic_id,
#                 topic_label=spec["label"],
#                 page=best.page,
#                 bbox=best.bbox(),
#                 anchor_text=best.text[:320],
#                 context_text=context_text,
#                 score=round(score, 3),
#                 confidence=_confidence(score),
#                 source_type=best.source_type,
#             )
#         )

#     # Reading order matters because each agent's rolling memory follows the document.
#     matches.sort(key=lambda m: (m.page, m.bbox[1]))
#     return matches

def detect_topics(blocks: List[TextBlock]) -> List[TopicMatch]:
    matches: List[TopicMatch] = []

    for topic_id, spec in TOPICS.items():
        ranked = []

        for block in blocks:
            score = _adjusted_topic_score(
                topic_id,
                block,
                blocks,
                spec,
            )

            if score > 0:
                ranked.append((score, block))

        if not ranked:
            continue

        ranked.sort(
            key=lambda x: (
                -x[0],
                x[1].page,
                x[1].y0,
            )
        )

        if topic_id == "course_overview":
            print("\n--- COURSE OVERVIEW CANDIDATES ---")

            for candidate_score, candidate_block in ranked[:10]:
                print("Score:", candidate_score)
                print("Source:", candidate_block.source_type)
                print("Page:", candidate_block.page + 1)
                print("Text:", candidate_block.text)
                print("---")

            print("----------------------------------\n")

        score, best = ranked[0]

        # print("\n--- TOPIC MATCH DEBUG ---")
        # print("Topic:", spec["label"])
        # print("Score:", score)
        # print("Source type:", best.source_type)
        # print("Page:", best.page + 1)
        # print("Anchor text:")
        # print(best.text)
        # print("-------------------------\n")

        # -------------------------------------------------------
        # Build context from the SAME region used as the anchor.
        # This prevents the agent reaction and PDF highlight
        # from drifting apart.
        # -------------------------------------------------------
        context_text = _context_for(
            blocks,
            best,
            radius=1,
        )

        # -------------------------------------------------------
        # Special handling for the semester schedule.
        # Schedule tables can span multiple pages.
        # -------------------------------------------------------
        if topic_id == "schedule":
            schedule_tables = [
                block
                for candidate_score, block in ranked
                if (
                    block.source_type == "table"
                    and _looks_like_schedule_table(block.text)
                )
            ]

            unique_tables = []
            seen = set()

            for table_block in sorted(
                schedule_tables,
                key=lambda b: (
                    b.page,
                    b.y0,
                    b.x0,
                ),
            ):
                key = (
                    table_block.page,
                    _norm(table_block.text)[:240],
                )

                if key in seen:
                    continue

                seen.add(key)
                unique_tables.append(table_block)

            if unique_tables:
                pieces = []

                for tb in unique_tables:
                    pieces.append(
                        f"[Schedule table - PDF page {tb.page + 1}]\n"
                        f"{tb.text}"
                    )

                context_text = "\n\n".join(pieces)[:16000]

                # Make sure the actual visual anchor is a schedule table,
                # not some unrelated sentence containing the word schedule.
                best_schedule = max(
                    unique_tables,
                    key=lambda tb: _score_block(
                        tb.text,
                        TOPICS["schedule"],
                    ),
                )

                best = best_schedule

        matches.append(
            TopicMatch(
                topic_id=topic_id,
                topic_label=spec["label"],

                # Highlight comes directly from the selected source.
                page=best.page,
                bbox=best.bbox(),

                # Text shown under:
                # "Why is this reaction placed here?"
                anchor_text=best.text[:500],

                # Text actually sent to Abi / Tim.
                context_text=context_text,

                score=round(score, 3),
                confidence=_confidence(score),
                source_type=best.source_type,
            )
        )

    # Preserve reading order so agent memory follows syllabus order.
    matches.sort(
        key=lambda m: (
            m.page,
            m.bbox[1],
        )
    )

    return matches


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    document_id: str,
    zoom: float = 1.6,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> List[str]:
    doc = fitz.open(pdf_path)
    target = output_dir / document_id
    target.mkdir(parents=True, exist_ok=True)
    result = []
    page_count = max(1, len(doc))

    matrix = fitz.Matrix(zoom, zoom)
    for page_idx, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out = target / f"page_{page_idx + 1}.png"
        pix.save(out)
        result.append(str(out))
        if progress_callback:
            pct = 22 + round(((page_idx + 1) / page_count) * 8)
            progress_callback("Rendering PDF pages", pct, f"Rendered page {page_idx + 1} of {page_count}")
    doc.close()
    return result


def process_pdf(
    pdf_path: Path,
    rendered_root: Path,
    progress_callback: Optional[Callable[[str, int, str], None]] = None,
) -> ProcessedDocument:
    document_id = uuid.uuid4().hex[:12]
    if progress_callback:
        progress_callback("Reading syllabus", 8, "Extracting text and detecting tables")
    blocks, sizes = extract_blocks(pdf_path)

    if progress_callback:
        progress_callback("Finding syllabus concepts", 18, f"Scanning {len(blocks)} text/table blocks")
    matches = detect_topics(blocks)

    if progress_callback:
        progress_callback("Preparing document", 22, f"Found {len(matches)} syllabus concepts")
    rendered = render_pages(
        pdf_path, rendered_root, document_id, progress_callback=progress_callback
    )
    return ProcessedDocument(
        document_id=document_id,
        filename=pdf_path.name,
        page_sizes=sizes,
        rendered_pages=rendered,
        topic_matches=[asdict(m) for m in matches],
    )
