# Security Notes

API keys are stored in a YAML file mapped by tenant slug to a SHA-256 token hash.
Use `scripts/generate_api_key.py` to generate a token and distribute the plain
text to the tenant. Rotate keys by editing `keys.yaml` and reloading the
application. We recommend encrypting the YAML with `sops` or a similar tool when
committing to Git.
