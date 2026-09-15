# Gharownda Agent Kit

Gharownda Agent Kit is a public, reusable framework for bounded AI-assisted software development.

It is designed around a strict authority boundary:

- maintainers define architecture, policy, task scope, acceptance criteria, and protected paths;
- workers implement one bounded task at a time;
- deterministic verification decides whether fixed checks pass;
- an independent reviewer audits the verified candidate;
- only the exact reviewed candidate may be published;
- workers and reviewers may not rewrite the rules that govern their own work.

The project deliberately contains no Gharownda private application source, credentials, production data, or private product requirements.

## Local CLI

The repository can be installed as a Python package and exposes `gak`, a small command-line interface for validating the same bounded task contracts used by the Actions runtime.

```bash
python -m pip install git+https://github.com/Gharownda/gharownda-agent-kit.git
```

Validate a task manifest in another repository:

```bash
gak --target-root /path/to/repository \
  validate-task agent/tasks/example.json
```

Validate a candidate JSON proposal against that task's editable-file allow-list:

```bash
gak --target-root /path/to/repository \
  validate-proposal agent/tasks/example.json /tmp/proposal.json
```

The CLI returns a small JSON summary on success and exits non-zero when the manifest, context, paths, or proposal violate the trusted contract. It does not run model inference or grant any extra authority.

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

The same contract runtime is usable locally through `gak` and by the public GitHub Actions coordinator.

## Model

The initial qualified worker/reviewer configuration uses Qwen3-14B Q4 through `llama.cpp` on standard public GitHub-hosted Linux runners. Model choice is runtime configuration, not part of the task contract.

## Safety model

Tasks are checked-in JSON manifests. They explicitly list context files, editable files, acceptance criteria, and deterministic test commands. The runtime rejects edits outside the allow-list and treats repository content as untrusted data rather than instructions.

See [`AGENTS.md`](AGENTS.md), [`docs/GOVERNANCE.md`](docs/GOVERNANCE.md), and [`docs/PRIVATE_TARGETS.md`](docs/PRIVATE_TARGETS.md) for the contributor, governance, and private-target security boundaries.
