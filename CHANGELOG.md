# Changelog

## 0.5.2

- The repository self-check covers the same directory scope as `gofmt -l .` and uses structured Go test results for its mutation experiments.
- `invaris init` and `invaris init --dry-run` explain the difference between the harness format and the CLI release. New guard harnesses still use `invaris.dev/v1alpha2`, and the dry run still sends only JSON to stdout.
- `invaris doctor` warns when it loads a `v1alpha1` harness and shows how to preview and apply a migration. The warning does not change the exit status.
- The quickstart previews a new harness and the [harness reference](docs/harness-spec.md#configuration-versions) explains which formats to use.

## 0.5.1

Fixes found by running 0.5.0 end to end on a real NestJS/Next.js remaster with Evaris. Report versions, decisions and exit codes are unchanged.

### Fixed

- `invaris test-result` could not feed a mutation run whose `testIds` select part of a suite: it printed every test, and `mutate` requires exactly the selected ones, so the experiment was `INCONCLUSIVE` (`malformed_evidence`). Running only the selected test instead breaks suites whose tests share state. New repeatable `--test-id ID` keeps only the named tests, in order, while the whole suite runs; a missing or skipped selected test exits `2`. See [test-result converters](docs/harness-spec.md#test-result-converters).
- The `malformed_evidence` stage detail for a test result with the wrong number of tests now says how many tests it had, how many the harness selects, and to use `--test-id`.
- `invaris ACTION --help` and `-h` now print that action's usage and exit `0` instead of `unknown flag` with exit `2`.

### Added

- `invaris validity-result tsc <executable> <tsconfig.json>` converts a TypeScript check into mutation validity evidence and distinguishes source diagnostics from an inconclusive setup failure.
- `invaris explain` items carry optional `details`: for a mutation or campaign experiment that was neither killed nor survived, the failed stage's recorded detail and the baseline tests that did not pass, so the cause no longer needs the raw report. The explanation schema gains the optional field. See [diagnostics](docs/diagnostics.md#json).

## 0.5.0

Closing the gaps found when Invaris was used on a real Node project. Default inputs, report versions and verification exit codes are unchanged; new fields are optional and omitted when unused.

### Added

- `invaris --help` (also `-h`, `help`) prints usage to stdout and exits 0, and `invaris --version` (also `version`) prints `invaris <version>`: the linked release, the module version, or `dev`.
- `"operator": "delete"` in v1alpha3 mutation harnesses removes the single occurrence of `before` (omit `after` or set it to `""`), so deleting a guard line no longer needs a stand-in replacement. Mutation evidence v1alpha3–v1alpha5 accepts `operator: "delete"`; reports from `replace` harnesses are unchanged. Example: `examples/mutation/deleted.json`.
- `invaris test-result <go-test-json|jest-json|junit-xml> [FILE|-]` converts `go test -json`, jest or vitest JSON, and pytest JUnit XML into an `invaris.test-result/v1alpha1` object with exit `0`, `1` or `2`. A build failure, a timeout, a package or test file that fails outside its tests (such as `TestMain` exiting nonzero or a throwing `afterAll`), a suite that fails to load or a pytest setup error exits `2`, so it never counts as a killed mutant; skipped tests are left out. See [test-result converters](docs/harness-spec.md#test-result-converters).
- Structured inspection findings accept optional `ruleId`, `message` and `line`, which are copied into report findings. Reports gain an optional finding `line` (evidence schemas v1alpha2, v1alpha4 and v1alpha5); messages stay withheld in v1alpha5. A challenge proof for a structured command guard matches the finding's policy and path, whatever `ruleId` it reports.
- Campaign reports record the paths the harnesses' `workspace` blocks left out of the snapshot as `sourceIdentity.workspaceExclude`, and a raised entry bound as `workspaceMaxEntries`; `invaris explain` reports them as the `workspace-excluded` limit. Both fields are omitted when no harness declares a workspace block.
- `docs/ecosystem.md` gains the Evaris compatibility table, kept identical in Evaris `docs/invaris.md`.

### Compatibility notes

- Consumers that strictly decode findings, such as Evaris, must accept the optional `line` before they read reports from guards that emit it. Reports from guards that do not emit it are unchanged. Evaris 0.4.0 accepts it; Evaris 0.3.0 and earlier refuse such reports.

## 0.4.0

Making the first useful experiment approachable. Configuration discovery and the `init` destination change as described below; existing root-level configurations remain supported. Report versions and verification exit codes are unchanged. Build with Go 1.27.4 or later.

### Added

- New project configurations are created at `.invaris/invaris.json`. Commands prefer that path and fall back to a root-level configuration; `init` refuses to create a competing file when the legacy file exists. Campaigns also support configuration inside `.invaris`. See [authoring](docs/authoring.md).
- An `invaris-cli` npm package is available with the Linux and macOS executables and command provider. It requires Node.js 22.14 or later; see [installation](docs/installation.md#npm-installation-after-publication) for availability and npm commands.
- `invaris explain [--format text|json] REPORT` reads a saved report offline, validates it with the rules that wrote it, and says for each result whether the fault was `detected`, `missed`, `inconclusive`, `excluded` or not run, with the meaning and next step of its recorded reason and the limits of what the report shows. It runs nothing and refuses a tampered or unsupported report. See [diagnostics](docs/diagnostics.md).
- `invaris doctor [--format text|json] [HARNESS]` inspects a harness's setup without running any of its commands: supported actions, whether the directory can be copied into a workspace, whether each program resolves in the PATH its command would use, allowlisted variables that are unset, targets, edit markers, built-in operator eligibility, pinned preimages and writable paths. Every check says it executed nothing. See [diagnostics](docs/diagnostics.md).
- Schemas [`explanation-v1alpha1`](schemas/explanation-v1alpha1.schema.json) and [`doctor-v1alpha1`](schemas/doctor-v1alpha1.schema.json) for the JSON output of the two commands.
- An optional `workspace` block in v1alpha3 mutation and v1alpha4 challenge harnesses: `dependencies` links directories such as `node_modules` beside the copy instead of copying them, `exclude` leaves build output and tool caches out of the copy and its integrity snapshots, and `maxEntries` raises the 2000-entry bound up to 200000. Campaigns combine the blocks of the harnesses they reference. See [workspace options](docs/harness-spec.md#workspace-options).
- A `workspace_changed` stage detail now lists the changed paths (up to 20, marked `+`, `-` or `~`) instead of only "workspace manifest changed", and the entry-limit and symbolic-link refusals say which `workspace` field resolves them.
- A [self-check experiment](docs/experiments/self-check.md) that runs a gofmt guard, a detected and a missed guardrail challenge, a killed and a surviving mutant and a campaign against this repository, with its friction log (`selfcheck.*.json`).

### Compatibility notes

- `explain` exits `0` or `2`. `doctor` exits `0` when no check failed, `1` when a setup check failed and `2` for usage errors or an unreadable harness file. For `doctor`, `1` means a setup problem, not a rejected verification.
- Neither command accepts `--report`; they write no report. Their JSON is not evidence and carries no decision of its own.
- `explain` reads reports from v1alpha2 to v1alpha5. The report versions, harness versions and verdict meanings are unchanged.

## 0.3.0

Released 2026-11-15 as [v0.3.0](https://github.com/akkaraponph/invaris/releases/tag/v0.3.0).

Developer experience and trustworthy mutation verification. Default inputs, flags, report versions and exit codes (`0` ACCEPT, `1` REJECT, `2` REFUSE or error) are unchanged; everything below is additive or opt-in. Build with Go 1.27.4 or later.

### Added

- `invaris init` creates a starter `invaris.json` (`generic`, or `--preset go` with a `go test ./...` guard) and `invaris init --detect` reports project markers. It never runs project code or overwrites a file. See [create and upgrade harnesses](docs/authoring.md).
- `invaris migrate` converts a v1alpha1 harness to v1alpha2 with the same commands, writable targets, policies and effective gate (including weak marker evidence), refusing anything it cannot carry over. `--dry-run` previews; a real migration keeps an exact `.bak`, takes a lock and replaces atomically.
- `--format text|compact` for `check` and `challenge`, and `--format compact` for `campaign`. JSON stays the default and the `--report` file is always JSON. Output has no color or control sequences.
- `invaris.dev/v1alpha4` guard harnesses with built-in challenge operators `trailing-whitespace`, `crlf-injection` and `secret-leak-injection` (version `"1"`, pinned by `preimageSha256`), proven only with structured guard evidence. See the [operator catalog](docs/mutation-operators.md) and the [offline example](examples/operators/README.md).
- `invaris.evidence/v1alpha5`, a portable profile for every action: built-in mutation metadata with a stable reproduction identity, command digests, the engine version, per-guard and per-operator campaign effectiveness, and a privacy projection that withholds paths, arguments, output and free text. Automatic for v1alpha4 inputs; `--evidence-version v1alpha5` for others. See the [evidence reference](docs/evidence-schema.md#portable-profile-v1alpha5).
- Schemas [`harness-v1alpha4`](schemas/harness-v1alpha4.schema.json) and [`evidence-v1alpha5`](schemas/evidence-v1alpha5.schema.json). Older schemas are unchanged.

### Changed

- Workspace copies stop on cancellation between entries and 1 MiB chunks, remove the partial copy, and report `canceled` or `timeout` instead of `workspace_prepare_failed`.
- Release builds can link their version (`-X github.com/akkaraponph/invaris/internal/engine.releaseVersion=v0.3.0`), which `engineVersion` then reports.
- CI runs on pull requests to `staging` and `main` and on pushes to `main`, with separate format/vet, test (Linux and macOS), fuzz, Dependency-Cruiser and packaging jobs. Packaging builds the archives once and verifies them natively on Linux amd64, Linux arm64 and macOS arm64.
- Pushing a `vX.Y.Z` tag on `main` runs CI, builds and verifies the archives and publishes the GitHub release with `SHA256SUMS` and the prepared release notes.

### Compatibility notes

- Reports from a migrated harness say compatibility `native`, and its config digest changes.
- v1alpha5 consumers must read new fields; older consumers keep receiving the older versions unless they opt in. A v1alpha4 harness always produces v1alpha5, and an older binary refuses it.
- To undo a migration, review and restore the `.bak` file by hand.

## 0.2.0

Invaris 0.2.0 adds campaigns: several mutation and guardrail experiments run together from one frozen copy of the source, with repeats, separate mutation and guardrail scores, and an explicit acceptance decision. Build with Go 1.27.4 or later. The offline examples use a POSIX shell.

### Highlights

- Run `invaris campaign` with an [`invaris.campaign/v1alpha1`](schemas/campaign-v1alpha1.schema.json) file. A campaign references existing v1alpha3 mutation experiments and v1alpha2 structured challenges anywhere under its directory, copies that directory once into a frozen snapshot, and runs each selected experiment up to five times from fresh copies. Reports use [`invaris.evidence/v1alpha4`](schemas/evidence-v1alpha4.schema.json). See [Campaigns](docs/campaigns.md).
- Every attempt and its full child evidence is kept. Repeats are `CONSISTENT`, `MIXED` or `INCOMPLETE`; there is no voting.
- The mutation score (`killed / (killed + survived)`) and the guardrail proof rate (`proven / (proven + unproven)`) count consistent experiments once each and are `null` when nothing is eligible. They are never combined.
- A typed acceptance policy (`requireNoSurvivors`, `requireAllGuardrailsProven`, `requireNoInconclusive`, `requireNoMixed`, optional `requireNoInvalid` and `minMutationScore`) decides `ACCEPT`, `REJECT` or `REFUSE`. Incomplete or contradictory evidence refuses before any reject.
- CLI options: `--only ID` runs a recorded subset, `--format text` prints a summary, and `--parallel N` (1 to 8, default 1) runs attempts concurrently. Exit codes stay `0` ACCEPT, `1` REJECT, `2` REFUSE or error.
- Source identity: the snapshot manifest digest, one digest per evaluated directory, Git revision and dirty state. Optional campaign `tools` record tool versions such as `go version`.
- Cancellation stops further attempts, records canceled and unstarted work, removes the snapshot, and still writes a valid partial report.

### Evidence and compatibility

- `run`, `check`, `challenge` and `mutate` keep their inputs, exit codes and report versions.
- Proofs gain `reason` and `reasonCategory`, and mutation experiments gain `reasonCategory`, with one shared vocabulary (`result`, `setup`, `infrastructure`, `evidence`).
- Reports record `gitDirty`, a `sourceSnapshot` digest per proof and experiment, and per-observation `executable` (path and SHA-256), `timeoutSeconds` and `envAllowlist`. Unknown values are `null`.
- **Schema update:** these keys are required in the `invaris.evidence/v1alpha2` and `v1alpha3` schemas published with 0.1.0. Consumers that validate strictly against the 0.1.0 schemas must update.
- **Behaviour change in `challenge`:** a guard that writes into the workspace now yields `INCONCLUSIVE` (`workspace_changed`) instead of a proof. A structured guard that exits 0 or 1 with rejected output now gives reason `malformed_evidence` instead of `execution_failed`; the verdict stays `INCONCLUSIVE`.
- Add optional `preimageSha256` to the v1alpha3 mutation (a stale target is rejected before any write) and optional `minInspected` to structured command guards.

### Examples and verification

- Add [`examples/go-project`](examples/go-project/README.md): Go tests killing or missing a mutant, an import guard proving a challenge, and campaigns with six outcomes and a deterministic mixed-result fixture.
- Add campaigns for the shell mutation and forbidden-dependency examples. `scripts/smoke.sh` and `scripts/validate-schemas.py` cover every campaign file and report.
- Add a [design note](docs/decisions/0001-campaign-engine.md) for the campaign decisions, including why execution is not sandboxed and baselines are not reused.

## 0.1.0

Invaris runs trusted local workflows and turns guard challenges and single-mutant experiments into versioned JSON evidence. Build with Go 1.27.4 or later. The offline examples use a POSIX shell.

### Highlights

- Run a single explicit replacement with `invaris mutate`. The v1alpha3 harness declares the writable target, validity command, test command, and selected test IDs. The v1alpha3 report records test and validity evidence, before and after digests, and cleanup.
- Mutation exits are `KILLED` (0), `SURVIVED` (1), and `INVALID` or `INCONCLUSIVE` (2). A kill requires a passing baseline and a structured assertion failure on the valid mutant.
- Reject overlapping replacement matches and install replacement bytes without writing through hard links. The scoped forbidden-dependency fixture checks the expected policy, rule, and target.
- See the [single-mutant harness](docs/harness-spec.md#single-mutant-harness), [mutation evidence](docs/evidence-schema.md#mutation-experiments), and [execution limits](docs/threat-model.md).

### Execution, adapters, and compatibility

- Validate harnesses before direct execution as well as on load; reject ambiguous JSON and unsafe paths.
- Preserve v1alpha1 harness compatibility, including the shipped command and structured examples. Invalid direct calls that previously reached execution now return `REFUSE`.
- Preflight report destinations before executing commands. Publication remains subject to race-time failures.
- **Output migration:** the CLI now emits `invaris.evidence/v1alpha2` for both v1alpha1 and v1alpha2 harnesses; the v1alpha1 report (`results`, `status`) is no longer produced. See `docs/evidence-schema.md` for the field mapping. The exit code is now derived from the `decision` (`ACCEPT` 0, `REJECT` 1, `REFUSE` 2), with the same values as before.
- Add `invaris.dev/v1alpha2` harnesses (explicit trust mode, policy objects, gate with `failure-first`/`refusal-first` precedence, `redactEnv`, `storeSensitiveOutput`). v1alpha1 harnesses are unchanged.
- Typed checks, proofs and gate decisions (`internal/domain`); evidence validation, deterministic serialization, redaction of configured secrets and exclusive artifact persistence (`internal/evidence`). Missing required results or incomplete evidence can no longer yield `ACCEPT`.
- Publish `schemas/harness-v1alpha2.schema.json` and `schemas/evidence-v1alpha2.schema.json`; `scripts/validate-schemas.py` validates real CLI output against them.
- Fix: `runner.Result.FinishedAt` was never set (and command durations were consequently wrong); it is now recorded on every path.
- Add the [provider protocol](docs/adapter-protocol.md): one bounded JSON request and response per provider process. Validate UTF-8, single JSON values, request IDs, versions, provider identity, finding scope, and native exits. Include conformance tests, an external-provider test kit (`INVARIS_CONFORMANCE_PROVIDER`), and a Python example (`adapters/example/main.py`).
- Run v1alpha2 adapters, provider guards, and `requiredAdapters`. Discover each used provider once before steps run. Missing required capabilities refuse the run; unsupported optional guards are `NOT_RUN`. Provider failures, protocol errors, and identity changes cause refusal. Reports record discovery and provider identity. Execution order is steps, command guards, then provider guards.
- Add `invaris-command-provider`, a generic structured-command provider (`cmd/invaris-command-provider`) that preserves the command's native exit status and inspected counts and validates evidence, plus `examples/provider/invaris.json`.
- Add `internal/workspace` for restricted copying, one-file replacement with digests and manifest checks, and verified cleanup. Baseline and challenged checks use the same evaluator and copy. Revalidate the target after the baseline. Strong proofs require one finding matching the policy, rule, and path. Reports add `detail`, `mutation`, and `stages`; `PROVEN` requires a recorded mutation and an `OK` cleanup stage. Document the [threat model](docs/threat-model.md).
- `adapter.Call` now always sends `policyIds` and `scope` as arrays, never `null`.
- Verify Dependency-Cruiser 18.7.2 (MIT) end to end, including an ineffective-rule control, using the adapter lockfile.
- Add subprocess exit-contract tests and offline smoke checks. The release workflow targets Go 1.27.4 on Linux and macOS and runs pinned Dependency-Cruiser separately.
- Add a related-projects catalog of public open-source repositories.
