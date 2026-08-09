# Codex fixtures

These small, synthetic/sanitized fixtures model the public CLI shapes observed
for Codex standalone 0.146.1 and negative compatibility cases. They contain no
account, token, pair code, hostname, private path, or authentication file data.

Timeout, missing-command, and non-zero-exit behavior is represented by the fake
runner's typed result/exception rather than a fabricated output body.
