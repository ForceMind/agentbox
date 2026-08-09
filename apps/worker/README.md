# AgentBox Worker

The Phase 3 Worker connects to the control-plane database, checks migration
readiness, performs bounded expired/revoked Session cleanup, and shuts down on
`SIGINT`/`SIGTERM`. It does not consume Jobs, call a Helper or Runtime, spawn a
subprocess, or perform system operations.
