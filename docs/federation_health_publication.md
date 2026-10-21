# Federation Health publication

The Federation Health workflow generates its report on a GitHub-hosted runner
after verifying that non-interactive Administrator access is available. It
binds the report to the workflow run and publishes the two report files through
a pull request. A successful report-generation run does not mean that the
snapshot itself is fresh or healthy; inspect the report's status and source
window separately.

By default, the publisher uses the run's `GITHUB_TOKEN`. GitHub may require a
maintainer to approve checks for a pull request created with that token. The
workflow does not grant `actions: write` and does not approve its own checks.

## Optional unattended check delivery

To have GitHub start checks automatically for each generated report pull
request, configure a dedicated GitHub App:

1. Create an App and install it on the `SentientOS` repository only.
2. Grant repository permissions `Contents: Read and write` and `Pull requests:
   Read and write`. Do not grant Actions or administration permission.
3. Add repository Actions secrets `SENTIENTOS_FEDERATION_HEALTH_APP_CLIENT_ID` and
   `SENTIENTOS_FEDERATION_HEALTH_APP_PRIVATE_KEY`.
4. Add the repository Actions variable `SENTIENTOS_FEDERATION_HEALTH_USE_APP`
   with the value `1`.

The workflow mints an installation token scoped to `Zombinator85/SentientOS`
and those same two permissions. It uses that token only for report PR
publication. If the variable is unset, the existing `GITHUB_TOKEN` path remains
active. Keep the App private key in the repository secret store; never commit
or paste it into workflow inputs, source, issues, or construction evidence.

After enabling the App path, verify a real scheduled execution against the
current `main`, inspect its run-bound artifact, and confirm the automated PR's
checks start and complete on the exact head. Do not merge a report just because
its publication workflow succeeded.
