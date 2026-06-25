#!/usr/bin/env python3
"""Register local OpenAI-compatible TTS services in Open Notebook.

This script is intended for operator use from an Open Notebook runtime
environment. It is idempotent by service name/model/provider/type and keeps
host-specific URLs configurable through environment variables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import SecretStr

from open_notebook.ai.models import DefaultModels, Model
from open_notebook.database.repository import repo_query
from open_notebook.domain.credential import Credential

LOCAL_API_KEY_PLACEHOLDER = "local-openai-compatible-placeholder"


@dataclass(frozen=True)
class LocalTTSService:
    name: str
    model: str
    env_var: str
    default_url: str
    enabled_by_default: bool = True


SERVICES = [
    LocalTTSService(
        name="Local Kokoro TTS",
        model="kokoro-82m",
        env_var="OPEN_NOTEBOOK_LOCAL_TTS_KOKORO_URL",
        default_url="http://host.docker.internal:18880/v1",
    ),
    LocalTTSService(
        name="Local Chatterbox TTS",
        model="chatterbox-tts",
        env_var="OPEN_NOTEBOOK_LOCAL_TTS_CHATTERBOX_URL",
        default_url="http://host.docker.internal:18882/v1",
    ),
    LocalTTSService(
        name="Local Orpheus TTS",
        model="orpheus-3b",
        env_var="OPEN_NOTEBOOK_LOCAL_TTS_ORPHEUS_URL",
        default_url="http://host.docker.internal:18883/v1",
    ),
    LocalTTSService(
        name="Local Dia TTS",
        model="dia-1.6b",
        env_var="OPEN_NOTEBOOK_LOCAL_TTS_DIA_URL",
        default_url="http://host.docker.internal:18884/v1",
        enabled_by_default=False,
    ),
]


def _service_url(service: LocalTTSService) -> str:
    return os.environ.get(service.env_var, service.default_url).rstrip("/")


async def _reachable(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/models")
            response.raise_for_status()
        return True
    except Exception:
        return False


async def _find_credential(name: str) -> Credential | None:
    rows = await repo_query(
        "SELECT * FROM credential WHERE name = $name AND provider = 'openai_compatible' LIMIT 1",
        {"name": name},
    )
    if not rows:
        return None
    return Credential._from_db_row(rows[0])


async def _ensure_credential(service: LocalTTSService, base_url: str) -> Credential:
    credential = await _find_credential(service.name)
    if credential is None:
        credential = Credential(
            name=service.name,
            provider="openai_compatible",
            modalities=["text_to_speech"],
            api_key=SecretStr(LOCAL_API_KEY_PLACEHOLDER),
            base_url=base_url,
            endpoint_tts=base_url,
        )
    else:
        credential.modalities = sorted(set(credential.modalities + ["text_to_speech"]))
        credential.base_url = base_url
        credential.endpoint_tts = base_url
        if credential.api_key is None:
            credential.api_key = SecretStr(LOCAL_API_KEY_PLACEHOLDER)
    await credential.save()
    return credential


async def _find_model(model_name: str) -> Model | None:
    rows = await repo_query(
        """
        SELECT * FROM model
        WHERE provider = 'openai_compatible'
          AND type = 'text_to_speech'
          AND name = $name
        LIMIT 1
        """,
        {"name": model_name},
    )
    if not rows:
        return None
    return Model(**rows[0])


async def _ensure_model(service: LocalTTSService, credential: Credential) -> Model:
    model = await _find_model(service.model)
    if model is None:
        model = Model(
            name=service.model,
            provider="openai_compatible",
            type="text_to_speech",
            credential=credential.id,
        )
    else:
        model.credential = credential.id
    await model.save()
    return model


async def register(
    default_model: str,
    check_reachability: bool,
    include_dia: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    registered_models: dict[str, Model] = {}

    for service in SERVICES:
        if not service.enabled_by_default and not include_dia:
            continue
        base_url = _service_url(service)
        reachable = await _reachable(base_url) if check_reachability else None
        credential = await _ensure_credential(service, base_url)
        model = await _ensure_model(service, credential)
        registered_models[service.model] = model
        results.append(
            {
                "service": service.name,
                "model": service.model,
                "base_url": base_url,
                "reachable": reachable,
                "credential_id": credential.id,
                "model_id": model.id,
            }
        )

    if default_model:
        if default_model not in registered_models:
            raise ValueError(
                f"Default model {default_model!r} is not one of: "
                f"{', '.join(sorted(registered_models))}"
            )
        defaults = await DefaultModels.get_instance()
        defaults.default_text_to_speech_model = registered_models[default_model].id
        await defaults.update()

    return {
        "registered": results,
        "default_text_to_speech_model": registered_models[default_model].id
        if default_model
        else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--default-model",
        default=os.environ.get("OPEN_NOTEBOOK_LOCAL_TTS_DEFAULT", "kokoro-82m"),
        help="Local TTS model to assign as default_text_to_speech_model.",
    )
    parser.add_argument(
        "--skip-reachability",
        action="store_true",
        help="Register records without checking each /v1/models endpoint first.",
    )
    parser.add_argument(
        "--include-dia",
        action="store_true",
        help="Also register the Dia OpenAI-compatible wrapper after it has been validated.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(
        register(
            default_model=args.default_model,
            check_reachability=not args.skip_reachability,
            include_dia=args.include_dia,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
