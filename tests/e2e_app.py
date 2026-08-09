"""Isolated API application used only by the Playwright harness."""

from __future__ import annotations

import os

from agentbox_api.main import create_app
from agentbox_core.configuration import Environment, Settings
from agentbox_core.security import PasswordManager
from agentbox_core.services import build_services

settings = Settings()
if settings.env is not Environment.TEST:
    raise RuntimeError("the Playwright API fixture requires AGENTBOX_ENV=test")

username = os.environ["AGENTBOX_E2E_USERNAME"]
password = os.environ["AGENTBOX_E2E_PASSWORD"]
services = build_services(
    settings,
    password_manager=PasswordManager(time_cost=1, memory_cost=8192, parallelism=1),
)
initialized, _existing_username = services.admin.status()
if not initialized:
    services.admin.initialize(username, password, request_id="req_e2e_bootstrap")

app = create_app(settings, services)
