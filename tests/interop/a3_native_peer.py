"""Bounded Node-to-supervisor control. Never a browser or production endpoint."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3_native_fixture import (  # noqa: E402
    A3NativeFixture,
    FixtureDirectory,
    fixture_error_diagnostic,
)


def emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)


def main() -> None:
    fixture: A3NativeFixture | None = None
    directory: FixtureDirectory | None = None

    def retain(owner: A3NativeFixture) -> None:
        nonlocal fixture
        fixture = owner

    try:
        for line in sys.stdin.buffer:
            if len(line) > 65536:
                raise ValueError("fixture request exceeded limit")
            request: dict[str, Any] = json.loads(line)
            op = request["op"]
            stage = "control"
            try:
                if op == "start":
                    stage = "static-directory"
                    if directory is not None:
                        raise ValueError("fixture may only start once")
                    import ipaddress

                    from cryptography import x509
                    from cryptography.hazmat.primitives import hashes, serialization
                    from cryptography.hazmat.primitives.asymmetric import rsa
                    from cryptography.x509.oid import NameOID

                    root = Path(request["root"])
                    static = Path(request["static_root"])
                    directory = FixtureDirectory(root, static)
                    isolated = request["isolated"]
                    if isolated:
                        directory.isolate_static()
                    stage = "certificate"
                    now = datetime.now(UTC)
                    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "A3 CI loopback")])
                    certificate = (
                        x509.CertificateBuilder()
                        .subject_name(name)
                        .issuer_name(name)
                        .public_key(key.public_key())
                        .serial_number(x509.random_serial_number())
                        .not_valid_before(now - timedelta(minutes=1))
                        .not_valid_after(now + timedelta(hours=1))
                        .add_extension(
                            x509.SubjectAlternativeName(
                                [x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
                            ),
                            critical=False,
                        )
                        .sign(key, hashes.SHA256())
                    )
                    # Disposable HTTPS TEST key is confined to supervisor/static server.
                    # It is unrelated to the A3 key and never enters API/Runtime.
                    stage = "process-start"
                    fixture = A3NativeFixture(
                        root / "processes",
                        origin=request["origin"],
                        static_root=static,
                        isolated=isolated,
                        retain=retain,
                    )
                    result: Any = {
                        "api_origin": fixture.api_origin,
                        "proof": fixture.proof,
                        "certificate": certificate.public_bytes(
                            serialization.Encoding.PEM
                        ).decode(),
                        "tls_key": key.private_bytes(
                            serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption(),
                        ).decode(),
                    }
                elif op == "close":
                    stage = "supervisor-cleanup"
                    if directory:
                        directory.close(fixture)
                    elif fixture:
                        fixture.close()
                    fixture = None
                    # Acknowledge only after child exit and privileged filesystem
                    # cleanup have both completed; Node never deletes UID-owned data.
                    emit({"id": request["id"], "ok": True, "result": {"cleaned": True}})
                    break
                else:
                    if fixture is None:
                        raise ValueError("fixture unavailable")
                    result = fixture.call(op, request.get("payload"))
                emit({"id": request["id"], "ok": True, "result": result})
            except Exception as error:
                # Fixed type only; never exception values, raw records or credentials.
                diagnostic = fixture_error_diagnostic(error)
                emit({"id": request["id"], "ok": False, "stage": stage, **diagnostic})
    finally:
        if directory:
            directory.close(fixture)
        elif fixture:
            fixture.close()


if __name__ == "__main__":
    main()
