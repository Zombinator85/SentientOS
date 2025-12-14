# Cloud Deployment Guide

This guide outlines a minimal setup for deploying the OpenAI connector using popular PaaS hosts.

## Render
1. Create a new **Web Service** from your repository.
2. Set the environment variables `CONNECTOR_TOKEN` and `PORT` under **Environment**.
3. Use the provided `Dockerfile` build option.
4. Expose the service on the port specified by `PORT`.

## Railway
1. Create a new project and link this repository.
2. Add `CONNECTOR_TOKEN` and `PORT` variables in the project settings.
3. Railway automatically builds the `Dockerfile` and deploys the container.
4. Open the generated URL to access the connector endpoints.

After deployment run `python smoke_test_connector.py` in the container shell to
verify the connector and review `logs/openai_connector.jsonl` for any `auth_error`
entries. Rotate logs may have numerical suffixes.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
