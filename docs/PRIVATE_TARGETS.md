# Private-target runner architecture

This document defines how the public Agent Kit may provide GitHub-hosted compute for a private target repository without making private application material public.

## Objectives

- Run expensive model inference and independent model review from this public repository.
- Keep target-repository source, task packets, prompts, patches, test output, and product details out of public artifacts and commits.
- Use the private repository's GitHub Actions primarily for trusted application CI and merge gates.
- Preserve maintainer ownership of architecture, privacy/auth/security policy, governance, and merges.
- Keep bounded work moving without requiring a human to manually launch every worker.

## Trust boundary

A public workflow may access a private target only through an explicitly configured repository secret. For Gharownda the intended secret name is `GHAROWNDA_APP_TOKEN`.

The credential must be a fine-grained token restricted to the target repository. Do not use a general-purpose personal token. Prefer a GitHub App installation token when the integration is mature enough to mint short-lived credentials.

Minimum intended repository permissions:

- **Contents: Read and write** — clone the private target, create short-lived private work leases, and push an `agent/*` proposal branch.
- **Pull requests: Read and write** — inspect duplicate/open proposals and open/update the proposal PR.
- **Actions: Read** — inspect target CI state when repair selection needs it.

No Administration, Secrets, Environments, Packages, Deployments, or organization-level permissions are required by the worker lane.

The target credential is available only to short privileged steps: private checkout, work selection/lease, existing-branch fetch, trusted feedback collection, publication, and lease cleanup. Worker inference, model-generated code, deterministic test commands, and reviewer inference run without the credential in their environment or persisted Git configuration.

## Execution model

```text
PRIVATE TARGET                         PUBLIC AGENT KIT
--------------                         ----------------
checked-in queue / open agent PRs
        |
        | authenticated read/lease
        +-----------------------------> coordinator every 30 minutes
                                         |
                                         +-- up to five isolated slots
                                         +-- repairs before new work
                                         +-- private lease prevents duplicates
                                         +-- bounded worker/repair inference
                                         +-- deterministic targeted verification
                                         +-- independent review
                                         +-- publish exact reviewed candidate
                                         |
        <----------------------------- push/update agent/* branch
        <----------------------------- open/update private PR
        |
private application CI
maintainer review
merge policy
```

The public repository supplies generic runtime and compute. The private repository remains the source of product truth.

## No-public-artifact rule

Private-target runs must not upload worker records, prompts, candidate patches, verification reports, source archives, review records, or private task descriptors as Actions artifacts in this public repository.

All private intermediate records live only on the ephemeral runner under temporary paths. Evidence required by the maintainer belongs in the private proposal/PR or private CI. Public job names expose only generic worker slot numbers.

## Logging

Private-target workflows must:

- disable shell tracing;
- never echo credentials or authenticated remote URLs;
- avoid printing prompts, source files, patches, task names, model context, or private test fixtures;
- keep model/runtime download logs separate from private context where practical;
- use synthetic test data;
- fail closed before inference if the credential, target allow-list, task manifest, edit allow-list, or lease is invalid.

Verification commands are captured rather than blindly streamed because arbitrary test output may contain private application details. Model prose never substitutes for deterministic test results.

## Continuous dispatch

The coordinator runs every 30 minutes as a watchdog and may also be redispatched after successful publication so free slots can refill without waiting for the next cron tick.

Each coordinator run exposes five generic slots. Every slot independently attempts to claim the highest-priority eligible private work using an atomic private lease. This allows slots to race without publishing task identifiers to the public Actions UI and prevents duplicate workers from owning the same task or repair.

Private leases use opaque hashes rather than task identifiers and expire after six hours. Only leases carrying the Agent Kit lease commit marker are eligible for automatic stale cleanup; unknown refs are never deleted automatically.

Priority order is:

1. Existing bounded `agent/*` PR with trusted maintainer changes requested.
2. Existing bounded `agent/*` PR with deterministic target CI failure.
3. New enabled `worker-with-review` task from the private queue.

Any open private PR carrying the same trusted task marker suppresses dispatch of a duplicate new worker, even when that PR was opened by a maintainer rather than an agent.

Maintainer-only and maintainer-led architecture/security work is never promoted into this autonomous lane merely because a queue entry or comment exists.

Trusted repair feedback is collected in a privileged step and written to an ephemeral local file. The repair model cannot query GitHub directly and receives only feedback from the configured trusted maintainer identities plus locally reproduced deterministic test evidence.

## Repair lifecycle

A repair worker checks out the existing private `agent/*` proposal, stays inside the original task's editable-file contract, reproduces targeted verification, proposes a bounded repair, runs the full deterministic task verification, receives an independent model review, and then updates the same private PR branch.

An agent PR receives at most **two automated repair commits** after its initial proposal. A third unresolved failure is left for maintainer intervention instead of consuming public runners indefinitely.

## Parallelism and quota isolation

Agent Kit runs at most five independent private-target worker lanes at a time. GitHub job concurrency serializes each generic slot across overlapping cron/refill runs, while private work leases prevent task duplication across slots.

The private target does not host model inference/reviewer jobs. Its Actions usage is reserved for application CI, trusted private checks, and merge gates.

## UI-model qualification

UI/UX model qualification is a separate public, synthetic benchmark. It must never use private screenshots, product requirements, or family data. Winning UI models may later be used as bounded visual generation/review specialists against private work through this same credential-isolated target pattern.

## Migration from private-hosted workers

1. Configure the least-privilege target credential as an Agent Kit repository secret.
2. Prove authenticated private checkout from a public runner without persisted credentials.
3. Enable the continuous coordinator and prove one bounded private proposal end-to-end.
4. Prove one repair cycle against trusted maintainer feedback.
5. Retire expensive private worker/reviewer workflows while keeping private Rails CI and governance gates intact.
6. Keep the 30-minute coordinator as watchdog and successful-publication refill as the faster path.

Do not weaken private repository gates to complete this migration.
