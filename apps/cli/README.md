# AgentBox CLI

The Phase 3 CLI provides read-only control-plane `status`/`doctor`, local-TTY
`admin init`, `admin status`, and CSPRNG `secret generate`. It does not accept a
password on argv, invoke host tools, or provide direct Runtime/Helper mutation.
