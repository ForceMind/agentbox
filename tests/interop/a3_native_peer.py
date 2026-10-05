"""Bounded Node-to-supervisor control. Never a browser or production endpoint."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from a3_native_fixture import A3NativeFixture  # noqa: E402


def emit(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)


def main() -> None:
    fixture: A3NativeFixture | None = None
    static: Path | None = None
    owner: tuple[int, int] | None = None
    try:
        for line in sys.stdin.buffer:
            if len(line) > 65536:
                raise ValueError("fixture request exceeded limit")
            request: dict[str, Any] = json.loads(line)
            op = request["op"]
            try:
                if op == "start":
                    import ipaddress

                    from cryptography import x509
                    from cryptography.hazmat.primitives import hashes, serialization
                    from cryptography.hazmat.primitives.asymmetric import rsa
                    from cryptography.x509.oid import NameOID

                    root = Path(request["root"])
                    static = Path(request["static_root"])
                    owner = (static.stat().st_uid, static.stat().st_gid)
                    isolated = request["isolated"]
                    if isolated:
                        if os.geteuid() != 0:
                            raise PermissionError("CI isolation root missing")
                        for path in (static / "index.html", static):
                            os.chown(path, 0, 0)
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
                    fixture = A3NativeFixture(
                        root / "processes",
                        origin=request["origin"],
                        static_root=static,
                        isolated=isolated,
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
                    if fixture:
                        fixture.close()
                        fixture = None
                    emit({"id": request["id"], "ok": True, "result": {}})
                    break
                else:
                    if fixture is None:
                        raise ValueError("fixture unavailable")
                    result = fixture.call(op, request.get("payload"))
                emit({"id": request["id"], "ok": True, "result": result})
            except Exception as error:
                # Fixed type only; never exception values, raw records or credentials.
                emit({"id": request["id"], "ok": False, "code": type(error).__name__})
    finally:
        if fixture:
            fixture.close()
        if static and owner and os.geteuid() == 0:
            for path in (static / "index.html", static):
                os.chown(path, *owner)
            static.chmod(0o755)


if __name__ == "__main__":
    main()
