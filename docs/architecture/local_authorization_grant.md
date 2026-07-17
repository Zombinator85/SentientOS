
## Readiness runtime boundary

`host_live_grant_readiness_runtime` deliberately does not call local authorization grant builders from `sentientosd`. Its approval packets and preflight receipts are review metadata only and cannot automatically convert readiness into a local authorization grant.
