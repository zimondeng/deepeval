"""Adapter for the third-party Jev decisions API."""

import asyncio
import json
import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

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
        proxy: Optional[str] = None,
        retry: int = 0,
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
        self.proxy = proxy
        self.retry = max(0, int(retry))
        self.last_attempts = 0
        self.last_usage: Optional[Dict[str, int]] = None
        self.last_answers: Optional[SystemOneAnswers] = None
        super().__init__(
            model or os.environ.get("JEV_MODEL", "typesafe/jev-1.14.0")
        )

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
        try:
            self.api_key.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RuntimeError(
                "JEV_API_KEY must contain only ASCII characters"
            ) from exc
        payload = {
            "model": self.name,
            "state": state,
            "questions": self._questions(questions),
        }
        request = Request(
            f"{self.base_url}/v1/decisions",
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "deepeval-local/1.0",
            },
            method="POST",
        )
        body = None
        for attempt in range(self.retry + 1):
            self.last_attempts = attempt + 1
            try:
                opener = (
                    build_opener(
                        ProxyHandler({"http": self.proxy, "https": self.proxy})
                    )
                    if self.proxy
                    else None
                )
                request_call = opener.open if opener else urlopen
                with request_call(request, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except (HTTPError, URLError) as exc:
                retryable = (
                    isinstance(exc, HTTPError)
                    and (exc.code == 429 or exc.code >= 500)
                ) or (
                    not isinstance(exc, HTTPError) and isinstance(exc, URLError)
                )
                if not retryable or attempt == self.retry:
                    detail = ""
                    if isinstance(exc, HTTPError):
                        detail = exc.read().decode("utf-8", errors="replace")[
                            :500
                        ]
                    raise RuntimeError(
                        f"third-party Jev request failed: {exc}. {detail}".strip()
                    ) from exc
                time.sleep((1, 3)[min(attempt, 1)])
        if body is None:  # pragma: no cover - loop either returns or raises
            raise RuntimeError("third-party Jev request returned no body")
        self.last_usage = body.get("usage")
        self.last_answers = self._answers(body.get("answers"))
        return self.last_answers, None

    async def a_decide(
        self, state: Any, questions: Dict[str, Any]
    ) -> Tuple[SystemOneAnswers, Optional[float]]:
        return await asyncio.to_thread(self.decide, state, questions)

    @staticmethod
    def _questions(questions: Dict[str, Any]) -> Dict[str, Any]:
        result = {}
        for key, question in questions.items():
            if hasattr(question, "options"):
                result[key] = {
                    "type": "choice",
                    "instructions": question.instructions,
                    "criteria": dict(question.options),
                }
            elif hasattr(question, "levels"):
                result[key] = {
                    "type": "score",
                    "instructions": question.instructions,
                    "criteria": list(question.levels),
                }
            else:
                criteria = None
                if (
                    getattr(question, "true", None) is not None
                    or getattr(question, "false", None) is not None
                ):
                    criteria = {
                        "true": getattr(question, "true", None),
                        "false": getattr(question, "false", None),
                    }
                result[key] = {
                    "type": "noul",
                    "instructions": question.instructions,
                }
                if criteria is not None:
                    result[key]["criteria"] = criteria
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
                answers.nouls[key] = NoulAnswer(
                    probability=float(answer["noul"])
                )
            elif answer_type == "choice":
                answers.choices[key] = ChoiceAnswer(
                    choice=str(answer["choice"]),
                    probabilities={
                        str(option): float(probability)
                        for option, probability in answer[
                            "probabilities"
                        ].items()
                    },
                    confidence=float(answer["confidence"]),
                )
            elif answer_type == "score":
                answers.scores[key] = ScoreAnswer(
                    score=float(answer["score"]),
                    probabilities={
                        int(level): float(probability)
                        for level, probability in answer[
                            "probabilities"
                        ].items()
                    },
                    confidence=float(answer["confidence"]),
                )
            else:
                raise RuntimeError(
                    f"third-party Jev answer {key!r} has unsupported type "
                    f"{answer_type!r}"
                )
        return answers
