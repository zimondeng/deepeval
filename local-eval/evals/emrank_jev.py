"""Adapter for the third-party Jev decisions API."""

import asyncio
import json
import os
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deepeval.models import DeepEvalBaseSystemOneModel
from deepeval.models.system_one.schema import (
    ChoiceAnswer,
    NoulAnswer,
    ScoreAnswer,
    SystemOneAnswers,
)


class EmrankJevModel(DeepEvalBaseSystemOneModel):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60,
    ):
        self.api_key = (
            api_key
            or os.environ.get("JEV_API_KEY", "").strip()
            or os.environ.get("OPENAI_API_KEY", "").strip()
        )
        self.base_url = (
            base_url or os.environ.get("JEV_BASE_URL", "https://emrank.tech")
        ).rstrip("/")
        self.timeout = timeout
        self.last_usage: Optional[Dict[str, int]] = None
        super().__init__(model or os.environ.get("JEV_MODEL", "typesafe/jev-1.14.0"))

    def load_model(self):
        return None

    def get_model_name(self):
        return f"{self.name} (emrank.tech)"

    def decide(
        self, state: Any, questions: Dict[str, Any]
    ) -> Tuple[SystemOneAnswers, Optional[float]]:
        if not self.api_key:
            raise RuntimeError(
                "JEV_API_KEY is not set; configure the third-party Jev key "
                "in local-eval/.env."
            )
        payload = {
            "model": self.name,
            "state": state,
            "questions": self._questions(questions),
        }
        request = Request(
            f"{self.base_url}/v1/decisions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "deepeval-local/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            detail = ""
            if isinstance(exc, HTTPError):
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"third-party Jev request failed: {exc}. {detail}".strip()
            ) from exc
        self.last_usage = body.get("usage")
        return self._answers(body.get("answers")), None

    async def a_decide(
        self, state: Any, questions: Dict[str, Any]
    ) -> Tuple[SystemOneAnswers, Optional[float]]:
        return await asyncio.to_thread(self.decide, state, questions)

    @staticmethod
    def _questions(questions: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, question in questions.items():
            if hasattr(question, "options"):
                criteria = {str(option): str(option) for option in question.options}
                result[key] = {
                    "type": "choice",
                    "instructions": question.instructions,
                    "criteria": criteria,
                }
            elif hasattr(question, "levels"):
                result[key] = {
                    "type": "score",
                    "instructions": question.instructions,
                    "criteria": list(question.levels),
                }
            else:
                result[key] = {
                    "type": "noul",
                    "instructions": question.instructions,
                }
        return result

    @staticmethod
    def _answers(raw: Any) -> SystemOneAnswers:
        if not isinstance(raw, dict):
            raise RuntimeError("third-party Jev response has no answers object")
        answers = SystemOneAnswers()
        for key, answer in raw.items():
            if not isinstance(answer, dict):
                raise RuntimeError(f"third-party Jev answer {key!r} is invalid")
            answer_type = answer.get("type")
            if answer_type == "noul":
                answers.nouls[key] = NoulAnswer(probability=float(answer["noul"]))
            elif answer_type == "choice":
                answers.choices[key] = ChoiceAnswer(
                    choice=str(answer["choice"]),
                    probabilities={
                        str(option): float(probability)
                        for option, probability in answer["probabilities"].items()
                    },
                    confidence=float(answer["confidence"]),
                )
            elif answer_type == "score":
                answers.scores[key] = ScoreAnswer(
                    score=float(answer["score"]),
                    probabilities={
                        int(level): float(probability)
                        for level, probability in answer["probabilities"].items()
                    },
                    confidence=float(answer["confidence"]),
                )
            else:
                raise RuntimeError(
                    f"third-party Jev answer {key!r} has unsupported type "
                    f"{answer_type!r}"
                )
        return answers
