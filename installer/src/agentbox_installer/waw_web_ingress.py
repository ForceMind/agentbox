"""Fixed independent HTTPS ingress; no API-controlled frontend or proxy target."""

from __future__ import annotations

import re
from urllib.parse import urlsplit


def render_web_ingress(origin: str) -> bytes:
    """Render a standalone nginx configuration for one canonical DNS Origin."""
    parsed = urlsplit(origin)
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or origin != "https://" + parsed.netloc
        or parsed.netloc != hostname + (f":{parsed.port}" if parsed.port else "")
        or origin != origin.lower()
        or len(hostname) > 253
        or any(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is None
            for label in hostname.split(".")
        )
        or parsed.port == 443
        or parsed.port is not None
        and not 1 <= parsed.port <= 65535
    ):
        raise ValueError("Web ingress requires a canonical HTTPS DNS Origin")
    port = parsed.port or 443
    # nginx does not inherit parent add_header directives when a location adds
    # its own. Repeat the complete static policy in every static location.
    csp = (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; worker-src 'none'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    headers = f"""add_header X-Content-Type-Options nosniff always;
        add_header Referrer-Policy no-referrer always;
        add_header Strict-Transport-Security \"max-age=31536000\" always;
        add_header Content-Security-Policy "{csp}" always;"""
    return f"""# AgentBox fixed HTTPS ingress v1; managed by agentbox-install.
worker_processes auto;
pid /run/agentbox-web/nginx.pid;
error_log stderr warn;
events {{ worker_connections 1024; }}
http {{
    access_log off;
    server_tokens off;
    default_type application/octet-stream;
    types {{
        text/html html;
        text/css css;
        application/javascript js;
        application/json json;
        image/svg+xml svg;
        image/png png;
        image/jpeg jpg jpeg;
        image/x-icon ico;
        font/woff2 woff2;
    }}
    client_body_temp_path /run/agentbox-web/client;
    proxy_temp_path /run/agentbox-web/proxy;
    map $http_upgrade $agentbox_connection {{ default close; websocket upgrade; }}
    server {{
        listen {port} ssl default_server;
        server_name {hostname};
        ssl_certificate /run/credentials/agentbox-web.service/fullchain.pem;
        ssl_certificate_key /run/credentials/agentbox-web.service/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        if ($http_host != "{parsed.netloc}") {{ return 421; }}
        root /var/lib/agentbox-web/current;
        {headers}
        location ^~ /api/v1/ {{
            proxy_pass http://127.0.0.1:8787;
            proxy_http_version 1.1;
            proxy_set_header Host "{parsed.netloc}";
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $remote_addr;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $agentbox_connection;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 60s;
            proxy_next_upstream off;
            proxy_ignore_headers X-Accel-Redirect X-Accel-Expires
                X-Accel-Limit-Rate X-Accel-Buffering;
            proxy_hide_header Content-Type;
            proxy_hide_header Content-Security-Policy;
            proxy_hide_header X-Content-Type-Options;
            proxy_hide_header Cache-Control;
            add_header Content-Type application/json always;
            add_header Cache-Control no-store always;
            add_header X-Content-Type-Options nosniff always;
            add_header Content-Security-Policy
                "default-src 'none'; sandbox; frame-ancestors 'none'" always;
            add_header Strict-Transport-Security "max-age=31536000" always;
        }}
        location = /.well-known/agentbox/waw-bootstrap.v1.json {{
            limit_except GET {{ deny all; }}
            try_files $uri =404;
            {headers}
            add_header Cache-Control no-store always;
        }}
        location ~ /\\. {{ return 404; }}
        location /api/ {{ return 404; }}
        location /assets/ {{
            limit_except GET {{ deny all; }}
            try_files $uri =404;
            {headers}
            add_header Cache-Control "public, max-age=31536000, immutable" always;
        }}
        location / {{
            limit_except GET {{ deny all; }}
            try_files /index.html =503;
            {headers}
            add_header Cache-Control no-store always;
        }}
    }}
}}
""".encode("ascii")
