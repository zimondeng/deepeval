"""Ephemeral credential transport and artifact redaction for local evaluation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Mapping

_SECRET_ENVIRONMENT = {
    "JEV_API_KEY",
    "OPENAI_API_KEY",
    "TARGET_API_KEY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
}


@dataclass(frozen=True)
class CredentialEnvelope:
    """Credentials passed once over stdin and never through process metadata."""

    jev_api_key: str | None = None
    target_headers: Mapping[str, str] = field(default_factory=dict)
    proxy: str | None = None

    def to_stdin(self) -> str:
        return json.dumps(
            {
                "jev_api_key": self.jev_api_key,
                "target_headers": dict(self.target_headers),
                "proxy": self.proxy,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_stdin(cls, stream) -> "CredentialEnvelope":
        value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("credential envelope must be an object")
        headers = value.get("target_headers", {})
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in headers.items()
        ):
            raise ValueError("target_headers must be a string map")
        return cls(
            jev_api_key=value.get("jev_api_key"),
            target_headers=headers,
            proxy=value.get("proxy"),
        )

    def command_environment(self) -> dict[str, str]:
        return {
            key: value
            for key, value in os.environ.items()
            if key not in _SECRET_ENVIRONMENT
        }

    @staticmethod
    def command_arguments() -> tuple[str, ...]:
        return ()


def redact_text(text: str, secrets: list[str] | tuple[str, ...]) -> str:
    for secret in sorted(
        (item for item in secrets if item), key=len, reverse=True
    ):
        text = text.replace(secret, "[REDACTED]")
    return text


def envelope_secrets(envelope: CredentialEnvelope) -> list[str]:
    return [
        envelope.jev_api_key or "",
        *envelope.target_headers.values(),
        envelope.proxy or "",
    ]
