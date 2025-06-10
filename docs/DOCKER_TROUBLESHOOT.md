# Docker Troubleshooting

If `docker compose up` fails on Windows with WSL path errors, ensure the project
folder is under the Linux filesystem (e.g. `/home/<user>/SentientOS`). You may
also need to enable file sharing for your drive in Docker Desktop settings.

If Docker isn't installed on your machine, simply skip `make docker-test`.
