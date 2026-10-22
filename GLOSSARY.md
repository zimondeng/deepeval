# Glossary

## Test Case

One evaluation input and the answer or trace produced by the system under test.

## Metric

A set of decision questions and scoring rules used to assess an evaluation subject.

## Question

A Noul, Choice or Score decision criterion with a weight. A Choice option may indicate that a criterion is not applicable.

## Model Config

Non-secret settings identifying the judgment model and how it is contacted.

## Credential

Secret information authorizing access to Jev, a target system or a proxy. A credential is not part of a saved evaluation configuration or report.

## Evaluation Engine Mode

The judgment mechanism. This console uses system_one. This is distinct from evaluation scope.

## Evaluation Scope

E2E assesses the final answer. Component assesses selected nodes in a trace with explicitly defined context.

## Trace and Span

A trace describes a system execution. A span describes one component operation and its relationship to other operations in that execution.

## Execution

One evaluation attempt, progressing from queued to running and then completed or failed, or through cancelling to cancelled. Completed means the evaluation finished, not that its quality passed.

## Verification Status

Whether real structured judgment results were obtained: not_verified, partial or verified. This does not imply acceptable quality.

## Quality Verdict

Whether a complete evaluation meets its configured quality requirements. An incomplete, failed or cancelled execution has no overall quality verdict.

## Report

The record of the evaluation inputs, execution outcome, verification status, quality verdict, detailed results and completeness. It contains no credentials.
