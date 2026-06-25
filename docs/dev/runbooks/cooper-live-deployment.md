# Runbook | Cooper Live Deployment

This runbook covers the local live instance served at:

- `https://open-notebook.ecochran.dyndns.org/`
- Docker container: `open-notebook-cooper`
- Docker image tag: `open-notebook:cooper`

Use it when a repo change must be visible on the live site. A pushed branch does not update the running site by itself.

## Preconditions

- Confirm this checkout is on the intended branch and commit.
- Keep live data, credentials, mounted Codex homes, and runtime state outside the repo.
- Do not print the contents of the runtime env file.
- If the task should not touch production-like local state, stop after repo validation and say the live deploy was intentionally skipped.

## Repo Validation

Run validation appropriate to the touched surface before rebuilding the live image.

```bash
git status --short --branch
uv run pytest tests/ -q
uv run ruff check .
cd frontend && npm run lint && npm run build
```

For narrower changes, a focused subset is acceptable, but the final handoff must say exactly what ran.

## Build

Build the single-container image from the same checkout and branch that contains the intended changes.

```bash
docker build \
  -f Dockerfile.single \
  --build-arg INSTALL_CODEX_CLI=true \
  -t open-notebook:cooper \
  .
```

## Recreate Container

Use the existing runtime env file and mounted runtime directories. Do not copy those files into the repo.

```bash
docker stop open-notebook-cooper || true
docker rm open-notebook-cooper || true

docker run -d \
  --name open-notebook-cooper \
  --restart unless-stopped \
  --env-file "$HOME/.local/share/open-notebook/runtime.env" \
  -p 127.0.0.1:15055:5055 \
  -p 127.0.0.1:18502:8502 \
  -v "$HOME/.local/share/open-notebook/data:/app/data" \
  -v "$HOME/.local/share/open-notebook/mydata:/mydata" \
  -v "$HOME/.local/share/open-notebook/codex-home:/codex-home" \
  open-notebook:cooper
```

## Health Checks

Verify the local container first.

```bash
docker ps --filter name=open-notebook-cooper
curl -fsS http://127.0.0.1:15055/health
curl -fsS http://127.0.0.1:18502/config
```

Then verify the public route.

```bash
curl -fsS https://open-notebook.ecochran.dyndns.org/config
```

For authenticated API checks, source the runtime env without echoing secrets.

```bash
set -a
. "$HOME/.local/share/open-notebook/runtime.env"
set +a

curl -fsS \
  -H "Authorization: Bearer $OPEN_NOTEBOOK_PASSWORD" \
  https://open-notebook.ecochran.dyndns.org/api/models/defaults
```

For Codex App Server and local model work, also verify:

```bash
curl -fsS \
  -H "Authorization: Bearer $OPEN_NOTEBOOK_PASSWORD" \
  https://open-notebook.ecochran.dyndns.org/api/models/codex-app-server/status

curl -fsS \
  -H "Authorization: Bearer $OPEN_NOTEBOOK_PASSWORD" \
  https://open-notebook.ecochran.dyndns.org/api/models
```

If a UI change was made, verify the changed page in a browser against the public URL, not only the local frontend port.

## Closeout Standard

Every live-site closeout should explicitly say:

- commit and branch deployed
- image tag rebuilt
- container recreated or restarted
- local health result
- public route result
- authenticated endpoint or browser check used for the changed behavior
- any skipped validation and why

