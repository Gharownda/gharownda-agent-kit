# Governance

The runtime uses checked-in task manifests as its source of authority. Model output is a proposal, not a command.

The normal autonomous lane must obey these controls:

- every task lists the files it may change;
- framework and workflow files are maintainer-controlled;
- test commands come from the checked-in task contract;
- verification runs after the worker proposes a change;
- a separate reviewer audits the verified candidate;
- publication must use the same candidate that was reviewed;
- merging remains a maintainer responsibility during qualification.

When a task needs to change governance or framework internals, it leaves the normal autonomous lane and becomes maintainer-led work.
