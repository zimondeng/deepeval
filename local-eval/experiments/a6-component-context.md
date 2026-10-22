# A6 Component context experiment

Status: **unverified**.

No real Jev-labeled Component dataset or human annotation set was available in
this implementation environment. The deterministic tests cover trace graph
validation, ID/parent/context preservation, native JevEval trace-state
conversion, question mapping, and incomplete-run aggregation guards; they do
not establish context quality, attribution accuracy, token use, or latency on
real labeled data.

The required follow-up is to freeze a labeled set, run each of the necessary
context, input/output-only, and full-trace variants at least three times per
sample, and record accuracy, attribution, token usage, elapsed time, and call
cost before selecting a default. Until that is done, no A6 quality conclusion
or `verified` claim is made.
