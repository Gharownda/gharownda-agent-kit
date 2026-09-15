# Gharownda Agent Kit

Gharownda Agent Kit is a public, reusable GitHub Actions framework for bounded AI-assisted software development.

It is designed around a strict authority boundary:

- maintainers define architecture, policy, task scope, acceptance criteria, and protected paths;
- workers implement one bounded task at a time;
- deterministic verification decides whether fixed checks pass;
- an independent reviewer audits the verified candidate;
- only the exact reviewed candidate may be published;
- workers and reviewers may not rewrite the rules that govern their own work.

The project deliberately contains no Gharownda private application source, credentials, production data, or private product requirements.

## Pipeline

```text
trusted task manifest
        |
        v
 bounded worker
        |
        v
 deterministic verification
        |
        v
 independent reviewer
        |
        v
 reviewed branch / pull request
        |
        v
 queue selects next eligible task
```

The initial runtime is derived from the bounded local-model harness previously proven in `faheemKamboh/multi-mail-mcp`, generalized here as an independent open-source project.

## Model

The initial qualified worker/reviewer configuration uses Qwen3-14B Q4 through `llama.cpp` on standard public GitHub-hosted Linux runners. Model choice is runtime configuration, not part of the task contract.

## Safety model

Tasks are checked-in JSON manifests. They explicitly list context files, editable files, acceptance criteria, and deterministic test commands. The runtime rejects edits outside the allow-list and treats repository content as untrusted data rather than instructions.

See [`AGENTS.md`](AGENTS.md), [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md), and [`docs/PRIVATE_TARGETS.md`](docs/PRIVATE_TARGETS.md) for the contributor, governance, and private-target security boundaries.
