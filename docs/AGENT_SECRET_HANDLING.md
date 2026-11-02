# Handling API keys in AI-agent workflows

AI agents may read terminal output, logs, and local files as part of normal work. Treat every value that enters an agent's context as potentially retained in the conversation or task trace.

## Recommended workflow

1. Keep the encrypted vault on a trusted machine and unlock it only for the duration of a task.
2. Give each agent only the credentials and scopes needed for that task. Prefer short-lived, revocable tokens where the provider supports them.
3. Retrieve a secret at the execution boundary. Pass it to the specific process that needs it rather than pasting it into a prompt, issue, pull request, or shared log.
4. Avoid shell tracing (`set -x`), command echoing, screenshots, and verbose HTTP logging around secret access.
5. Do not commit plaintext `.env` files, exported credential bundles, debug logs, or decrypted vault data. Review staged files before every push.
6. After a task, lock the vault, clean up temporary files, and rotate any credential that may have been exposed.

## CLI example

The following pattern keeps a secret out of the *prompt*, but does not make it invisible to the process environment or privileged local users:

```sh
# Run only inside a trusted local shell; do not enable shell tracing.
export OPENAI_API_KEY="$(apivault get OPENAI_API_KEY)"
# Run your application here, without printing the variable.
unset OPENAI_API_KEY
```

For unattended jobs, use the vault's documented password-file or standard-input options. Protect that input and restrict file permissions. Do not put master passwords or tokens in repository configuration.

## Local API considerations

- Prefer binding the vault HTTP API to `127.0.0.1`.
- Exposing it on `0.0.0.0` expands its attack surface; require authentication, a trusted network, and ideally a separately authenticated encrypted transport.
- Never include bearer tokens in PRs, copied command transcripts, issue reports, or application logs.
- A local bearer token is still sensitive even when the vault database is encrypted at rest.

## If a key leaks

Revoke or rotate the exposed credential at its provider, inspect recent usage, remove the leaked value from public locations, and assess whether logs or repositories require cleanup. Deleting a visible copy does not guarantee it has disappeared from history or external caches.

See [the project README](../README.md) and [API reference](API.md) for the product's actual CLI and HTTP API options.
