from __future__ import annotations

import json
import os
import re
import sys
from typing import Callable, Dict, List, Optional


PERSONAS = ["Abi", "Tim"]


def clean_json_response(raw_text: str) -> dict:
    text = raw_text.strip()

    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx : end_idx + 1]

    try:
        return json.loads(text, strict=False)

    except Exception:
        sanitized = re.sub(
            r"[\x00-\x1f\x7f-\x9f]",
            " ",
            text,
        )

        try:
            return json.loads(
                sanitized,
                strict=False,
            )

        except Exception:
            return {
                "internal_monologue": raw_text[:220],
                "interpretation": (
                    "The structured response could not be parsed."
                ),
                "questions_or_uncertainty": (
                    "Unable to determine from the response."
                ),
                "self_assessment": "No change",
                "immediate_next_step": (
                    "Continue reading the syllabus."
                ),
            }


def build_student_reading_prompt(
    persona,
    section_name: str,
    section_content: str,
    prior_reactions: List[str],
) -> str:

    core_beliefs = []

    if (
        hasattr(persona, "a_mem")
        and hasattr(
            persona.a_mem,
            "seq_thought",
        )
    ):
        for node in persona.a_mem.seq_thought:
            core_beliefs.append(
                f"- {node.description}"
            )

    baseline = (
        "\n".join(core_beliefs)
        if core_beliefs
        else (
            f"- {persona.scratch.innate}\n"
            f"- {persona.scratch.learned}"
        )
    )

    context = (
        "\n".join(
            f"- {reaction}"
            for reaction in prior_reactions[-3:]
        )
        if prior_reactions
        else (
            "Just opened the syllabus document "
            "for the first time."
        )
    )

    return f"""
You are simulating student '{persona.name}', who has just enrolled
in a course and is reading through the syllabus before the first
day of class.

### FOUNDATIONAL COGNITIVE BELIEFS & HABITS FROM MEMORY:

{baseline}

### PREVIOUS THOUGHTS FROM EARLIER SECTIONS OF THIS SYLLABUS:

{context}

### CURRENT SYLLABUS SECTION BEING READ:

[{section_name}]

{section_content}

### INSTRUCTIONS:

Read the section naturally as {persona.name}.

Respond based on the student's existing beliefs, habits, experiences, and previous reactions.

Describe what goes through the student's mind while reading this section and how the student understands what it means for them.

React naturally. Do not deliberately search for problems or assume that something must be confusing or difficult. If the section is clear or unremarkable, simply understand it and continue.

Base the response only on information explicitly present in the section. Do not infer or invent missing details; recognize placeholders or incomplete information as such.

Include any question, uncertainty, hesitation, or difficulty only if it naturally arises.

Describe what the student would realistically do next.

Respond strictly in valid JSON:

{{
  "internal_monologue": "Candid first-person thoughts while reading this section",

  "interpretation": "How the student understands what this section means for them",

  "questions_or_uncertainty": "Any question, uncertainty, hesitation, or confusion that naturally occurred. If none occurred, say None.",

  "self_assessment": "How capable or prepared you currently feel after reading this section, if this naturally changes. Otherwise say No change.",

  "immediate_next_step": "What the student would realistically do next after reading this section"
}}
"""


class TwoAgentRunner:
    """
    Adapter around the user's existing Generative Agents + Ollama code.

    Live mode expects the original project to be available locally
    and uses its Persona class plus
    persona.prompt_template.gpt_structure.GPT_request.

    Mock mode exists only so the frontend can be demonstrated
    independently.
    """

    def __init__(self):
        self.mock = (
            os.environ.get(
                "MOCK_AGENTS",
                "0",
            )
            == "1"
        )

        self.root = os.environ.get(
            "GENERATIVE_AGENTS_ROOT",
            "",
        )

        self.storage_base = os.environ.get(
            "PERSONA_STORAGE_BASE",
            "",
        )

        self.personas: Dict[str, object] = {}

        self.memories: Dict[
            str,
            List[str],
        ] = {
            name: []
            for name in PERSONAS
        }

        if not self.mock:

            if (
                not self.root
                or not self.storage_base
            ):
                raise RuntimeError(
                    "Set GENERATIVE_AGENTS_ROOT and "
                    "PERSONA_STORAGE_BASE, or set "
                    "MOCK_AGENTS=1 for UI testing."
                )

            if self.root not in sys.path:
                sys.path.insert(
                    0,
                    self.root,
                )

            from persona.persona import Persona
            from persona.prompt_template.gpt_structure import (
                GPT_request,
            )

            self.Persona = Persona
            self.GPT_request = GPT_request

            for name in PERSONAS:

                folder = os.path.join(
                    self.storage_base,
                    name,
                )

                if not os.path.exists(
                    folder
                ):
                    raise FileNotFoundError(
                        f"Persona folder not found: {folder}"
                    )

                self.personas[name] = Persona(
                    name,
                    folder,
                )

    def reset(self):
        self.memories = {
            name: []
            for name in PERSONAS
        }

    def _mock_output(
        self,
        name: str,
        label: str,
        content: str,
    ) -> dict:

        low = content.lower()

        if (
            "late" in low
            or "deadline" in low
            or "penalty" in low
        ):
            if name == "Abi":
                monologue = (
                    "I should make sure I understand exactly "
                    "when this is due. I usually prefer having "
                    "a little extra time in case something goes wrong."
                )

                interpretation = (
                    "Deadlines appear to be important and I will "
                    "need to plan ahead."
                )

                uncertainty = (
                    "I wonder what happens if I have a technical "
                    "problem close to the deadline."
                )

                action = (
                    "Record the deadline and plan to finish early."
                )

            else:
                monologue = (
                    "Okay, I need to keep track of this deadline "
                    "during the semester."
                )

                interpretation = (
                    "I need to submit the work by the stated deadline."
                )

                uncertainty = "None."

                action = (
                    "Add the deadline to my calendar and continue reading."
                )

        elif any(
            term in low
            for term in [
                "software",
                "programming language",
                "technology",
                "python",
                "java",
                "javascript",
                "c++",
                "c#",
                "matlab",
                "sql",
                "ide",
                "compiler",
            ]
        ):
            if name == "Abi":
                monologue = (
                    "There are some tools here that I may need "
                    "to learn before I feel comfortable using them."
                )

                interpretation = (
                    "The course expects me to use specific software "
                    "or technical tools."
                )

                uncertainty = (
                    "I am not completely sure how difficult the "
                    "initial setup will be."
                )

                action = (
                    "Look for setup instructions and try installing "
                    "the required tools."
                )

            else:
                monologue = (
                    "These look like tools I will need for the course. "
                    "I should make sure everything is installed."
                )

                interpretation = (
                    "The course requires specific software or tools."
                )

                uncertainty = "None."

                action = (
                    "Set up and verify the required tools before class."
                )

        else:
            monologue = (
                f"As {name}, I am reading '{label}' and figuring out "
                "what I need to remember for the semester."
            )

            interpretation = (
                "This section provides information I should keep "
                "in mind while taking the course."
            )

            uncertainty = "None."

            action = (
                "Make a note if needed and continue reading."
            )

        return {
            "internal_monologue": monologue,
            "interpretation": interpretation,
            "questions_or_uncertainty": uncertainty,
            "self_assessment": "No change",
            "immediate_next_step": action,
        }

    def run_topic(
        self,
        topic_label: str,
        context_text: str,
        progress_callback: Optional[
            Callable[
                [str, str, int, int],
                None,
            ]
        ] = None,
        completed_before: int = 0,
        total_calls: int = 0,
    ) -> Dict[str, dict]:

        evaluations = {}

        for offset, name in enumerate(
            PERSONAS
        ):

            current_call = (
                completed_before
                + offset
            )

            if progress_callback:
                progress_callback(
                    name,
                    topic_label,
                    current_call,
                    total_calls,
                )

            if self.mock:

                output = self._mock_output(
                    name,
                    topic_label,
                    context_text,
                )

            else:

                persona = self.personas[
                    name
                ]

                print("\n--- SECTION SENT TO AGENT ---")
                print("Agent:", name)
                print("Section:", topic_label)
                print(context_text)
                print("-----------------------------\n")


                prompt = (
                    build_student_reading_prompt(
                        persona,
                        topic_label,
                        context_text,
                        self.memories[name],
                    )
                )

                raw = self.GPT_request(
                    prompt
                )

                output = (
                    clean_json_response(
                        raw
                    )
                )

            memory = (
                f"Read '{topic_label}'. "
                f"Interpretation: "
                f"'{str(output.get('interpretation', ''))[:120]}'. "
                f"Thought: "
                f"'{str(output.get('internal_monologue', ''))[:120]}'. "
                f"Next step: "
                f"'{str(output.get('immediate_next_step', ''))[:100]}'."
            )

            self.memories[
                name
            ].append(
                memory
            )

            evaluations[
                name
            ] = output

            if progress_callback:

                progress_callback(
                    name,
                    topic_label,
                    current_call + 1,
                    total_calls,
                )

        return evaluations

    def run_document(
        self,
        topic_matches: List[dict],
        progress_callback: Optional[
            Callable[
                [str, str, int, int],
                None,
            ]
        ] = None,
    ) -> List[dict]:

        self.reset()

        results = []

        total_calls = (
            len(topic_matches)
            * len(PERSONAS)
        )

        completed = 0

        for match in topic_matches:

            item = dict(
                match
            )

            item[
                "evaluations"
            ] = self.run_topic(
                match[
                    "topic_label"
                ],
                match[
                    "context_text"
                ],
                progress_callback=(
                    progress_callback
                ),
                completed_before=(
                    completed
                ),
                total_calls=(
                    total_calls
                ),
            )

            completed += len(
                PERSONAS
            )

            results.append(
                item
            )

        return results