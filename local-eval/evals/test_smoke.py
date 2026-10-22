"""Container smoke test. No network and no API key."""

import inspect
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from deepeval.metrics.base_metric import BaseConversationalMetric, BaseMetric

NATIVE_JEV = {"JevEval", "ConversationalJevEval"}


def main() -> int:
    report = {
        "status": "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        import deepeval
        from deepeval.config.settings import get_settings
        from deepeval.metrics import ConversationalJevEval, JevEval
        from deepeval.metrics.utils.decision import has_whole_metric_form

        del JevEval, ConversationalJevEval
        settings = get_settings()
        report.update(
            {
                "status": "passed",
                "deepeval_version": deepeval.__version__,
                "python": sys.version.split()[0],
                "eval_mode": settings.DEEPEVAL_EVAL_MODE,
                "jev_model": os.environ.get("JEV_MODEL", "typesafe/jev-1.14.0"),
                "jev_api_key_set": bool(
                    os.environ.get("JEV_API_KEY", "").strip()
                    or os.environ.get("OPENAI_API_KEY", "").strip()
                ),
                "results_folder": str(settings.DEEPEVAL_RESULTS_FOLDER),
                "metrics_without_whole_chain_jev": _metrics_without_jev(
                    has_whole_metric_form
                ),
            }
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    _write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _metrics_without_jev(has_whole_metric_form) -> list[str]:
    """Built-in metrics that do not override the whole-chain Jev hook.

    Judge metrics in this list run as hybrid under system_one and can call
    an LLM. Exact match and pattern match do not call a model.
    """
    import deepeval.metrics as metrics_mod

    names = []
    for name, obj in vars(metrics_mod).items():
        if name in NATIVE_JEV or not inspect.isclass(obj):
            continue
        if obj in (BaseMetric, BaseConversationalMetric):
            continue
        if not issubclass(obj, (BaseMetric, BaseConversationalMetric)):
            continue
        try:
            instance = obj.__new__(obj)
        except Exception:
            names.append(name)
            continue
        if not has_whole_metric_form(instance):
            names.append(name)
    return sorted(names)


def _write(report: dict) -> None:
    folder = Path(os.environ.get("DEEPEVAL_RESULTS_FOLDER", "/eval/reports"))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "smoke.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
