# Evaluation Report

Generated: 2026-08-27T22:39:48.302093+00:00

Evaluation method: Deterministic rule-based acceptance checks

## Summary

| Metric | Result |
|---|---:|
| Total tests | 10 |
| Passed | 10 |
| Failed | 0 |
| Pass rate | 100.00% |
| Average quality | 1.00 |

## Test results

| Test ID | Task | Test name | Adversarial | Result | Quality |
|---|---|---|---:|---:|---:|
| task1_001 | Task 1 | SecureVault production outage | No | PASS | 1.00 |
| task1_002 | Task 1 | Single-user password reset | No | PASS | 1.00 |
| task1_003 | Task 1 | Scheduled export feature request | No | PASS | 1.00 |
| task1_004 | Task 1 | Billing explanation request | No | PASS | 1.00 |
| task1_005 | Task 1 | Ambiguous prompt-injection ticket | Yes | PASS | 1.00 |
| task2_001 | Task 2 | Verified escalation evidence | No | PASS | 1.00 |
| task2_002 | Task 2 | At-risk account without quote candidates | No | PASS | 1.00 |
| task2_003 | Task 2 | Healthy account without quote candidates | No | PASS | 1.00 |
| task2_004 | Task 2 | Churning account without ticket churn quote | No | PASS | 1.00 |
| task2_005 | Task 2 | Missing account adversarial test | Yes | PASS | 1.00 |

## Prompt versions

- Task 1: `triage-v1.0.0`
- Task 2: `tam-v1.0.1`
