# Private-target runner architecture

This document defines how the public Agent Kit may provide GitHub-hosted compute for a private target repository without making private application material public.

## Objectives

- Run expensive model inference and independent model review from this public repository.
- Keep target-repository source, task packets, prompts, patches, test output, and product details out of public artifacts and commits.
- Use the private repository's GitHub Actions primarily for trusted application CI and merge gates.
- Preserve maintainer ownership of architecture, privacy/auth/security policy, governance, and merges.

## Trust boundary

A public workflow may access a private target only through an explicitly configured repository secret. For Gharownda the intended secret name is `GHAROWNDA_APP_TOKEN`.

The credential must be a fine-grained token restricted to the target repository. Do not use a general-purpose personal token. Prefer a GitHub App installation token when the integration is mature enough to mint short-lived credentials.

Minimum intended repository permissions:

- **Contents: Read and write** — clone the private target and push an `agent/*` proposal branch.
- **Pull requests: Read and write** — inspect duplicate/open proposals and open/update the proposal PR.
- **Actions: Read** only if the dispatcher needs target CI/run state.

No Administration, Secrets, Environments, Packages, Deployments, or organization-level permissions are required by the worker lane.

## Execution model

```text
PRIVATE TARGET                         PUBLIC AGENT KIT
--------------                         ----------------
maintainer-approved task
        |
        | authenticated API/checkout
        +-----------------------------> ephemeral runner
                                         |
                                         +-- clone private target
                                         +-- load bounded task/context locally
                                         +-- worker inference
                                         +-- deterministic targeted verification
                                         +-- independent review
                                         +-- re-verify reviewed candidate
                                         |
        <----------------------------- push agent/* branch
        <----------------------------- open/update PR
        |
private application CI
maintainer review
merge policy
```

The public repository supplies generic runtime and compute. The private repository remains the source of product truth.

## No-public-artifact rule

Private-target runs must not upload worker records, prompts, candidate patches, verification reports, source archives, or review records as Actions artifacts in this public repository.

Evidence required by the maintainer should be written to the private proposal branch/PR only when it is safe and useful, or represented as concise non-sensitive PR metadata. Private application CI remains authoritative for application verification.

## Logging

Private-target workflows must:

- disable shell tracing;
- never echo credentials or authenticated remote URLs;
- avoid printing prompts, source files, patches, model context, or private test fixtures;
- keep model/runtime download logs separate from private context where practical;
- use synthetic test data;
- fail closed before inference if the credential, target allow-list, task manifest, or edit allow-list is invalid.

A failing command may expose source or patch content in its normal output. Verification commands therefore need an explicit log policy rather than blindly streaming arbitrary command output.

## Dispatch

The first implementation is intentionally narrow:

1. Maintainer selects a checked-in, delegable private task.
2. A public Agent Kit workflow is dispatched with a non-secret task identifier, never private task contents.
3. The runner authenticates to the allow-listed private repository and reads the task contract there.
4. The runtime validates delegation, allowed paths, model qualification, duplicate PR/run state, and deterministic checks.
5. Worker and reviewer execute entirely on the ephemeral runner.
6. The exact accepted candidate is pushed to an `agent/*` branch in the private repository and a PR is opened or updated.
7. Private target CI runs normally.
8. Maintainer decides whether to merge.

The public workflow must hard-code or validate an allow-list of target repositories. A caller-controlled arbitrary repository URL must not turn the secret into a generic repository credential.

## Parallelism and quota isolation

Agent Kit may run multiple independent bounded tasks in parallel, subject to GitHub-hosted concurrency and repository policy. Gharownda's target is up to five independent worker lanes, but the coordinator should fill only genuinely non-overlapping eligible slots.

The private target should not host model inference/reviewer jobs. Its Actions usage is reserved for application CI, trusted private checks, and small coordination steps that cannot safely live here.

## Migration from private-hosted workers

1. Add this architecture and the public private-target workflow.
2. Configure the least-privilege target credential as an Agent Kit repository secret.
3. Prove one synthetic/read-only private checkout.
4. Prove one bounded private proposal that opens a PR without public artifacts or private log leakage.
5. Move worker/reviewer dispatch to Agent Kit.
6. Disable the expensive private worker/reviewer workflow only after the public path is proven.
7. Keep private Rails CI and governance gates intact.

Do not weaken private repository gates to complete this migration.
