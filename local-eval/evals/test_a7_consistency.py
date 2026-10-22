from deepeval.metrics.jev_eval import Noul

from evals.execution import _questions


def test_a7_question_mapping_preserves_native_jev_question_shape():
    question = {
        "id": "q1",
        "type": "noul",
        "text": "The answer is relevant.",
        "true": "yes",
        "false": "no",
        "weight": 0.75,
    }

    mapped = _questions([question])

    assert isinstance(mapped[0], Noul)
    assert mapped[0].statement == question["text"]
    assert mapped[0].true == "yes"
    assert mapped[0].false == "no"
    assert mapped[0].weight == 0.75
