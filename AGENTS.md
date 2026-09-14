# Agent contributor contract

This repository contains the framework that governs bounded coding agents. Automated agents have less authority than maintainers and may not change the rules that evaluate their own work.

## Authority order

1. Maintainer decisions recorded in the repository.
2. Security and governance rules.
3. Checked-in task manifests under `agent/tasks/`.
4. Existing implementation details.

## Worker role

A worker may implement one trusted task manifest, edit only allow-listed files, make the smallest coherent change that satisfies the acceptance criteria, and report risks or blockers.

A worker may not modify `.github/`, `AGENTS.md`, `docs/SECURITY.md`, `agent/runtime/`, `agent/companion/`, model qualification policy, or queue governance through the normal autonomous lane. It may not weaken tests or verification, expand task scope, change architectural policy, or merge its own work.

## Reviewer role

The reviewer is independent from the worker. It audits every acceptance criterion, scope, deterministic evidence, security boundaries, and test integrity. It must not approve a candidate with unresolved material findings.

## Maintainer role

Maintainers own architecture, task decomposition, protected-path changes, queue policy, model qualification, merges, and repairs after bounded-worker failure.

## Public project boundary

Actions in this repository are for developing, testing, reviewing, and publishing this open-source project itself.
