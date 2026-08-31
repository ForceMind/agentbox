# Decision and Architecture Index

## Policy Decisions

- `GOV-AUTOMATION-1`: Mechanical release/merge/slice actions delegated to `agentbox-governance-bot` only with Owner approval in protected environment.
- `GOV-AUTOMATION-2`: Exact head/base/PR metadata required before any mechanical action.
- `GOV-AUTOMATION-3`: Host-gated operations require explicit host evidence and non-secret artifacts.

## Execution Notes

- Keep each governance execution as a separate Draft PR with Architecture/Security/Test review evidence.
