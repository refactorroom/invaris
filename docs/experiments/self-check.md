# Self-check experiment: Invaris on Invaris

This is the record of one real experiment run on this repository, written to find out where the workflow hurts. It is a log, not a success story: where something failed or needed a guess, it says so.

## Current harness (November 2026)

The record below describes the original run. The current formatting guard scans the repository root, including `examples`, hidden directories, `testdata`, `node_modules`, and `vendor`, and skips dot-prefixed Go files like `gofmt -l .`. It is a structured self-check and does not run the remaining CI checks (vet, tests, race, smoke, schema, fuzz, and adapter checks).

The mutation harnesses run the three selected Go tests with `go test -json` and convert their actual results with the installed `invaris test-result go-test-json`. They explicitly list the resulting parent and subtest IDs; when those tests change, update the list to match the converter output. This requires Invaris on `PATH`. The installed v0.5.0 converter does not support the `--test-id` filtering described by newer repository documentation. The deliberate missed-detection controls remain in the campaign, so its strict acceptance policy is expected to reject even when the controls behave as intended.

## The concern, and why

Invaris claims it can show whether a guard or a test suite notices a deliberate fault. The roadmap asks for that claim to be exercised on a project that is not a purpose-built fixture. The experiment uses this repository with three parts:

- a healthy baseline: a guard that passes on the unmodified tree;
- a deliberate fault the guard must detect (expected `PROVEN`, `KILLED`);
- a missed-detection control: a fault the guard cannot see, so a missed outcome is demonstrated rather than assumed (expected `UNPROVEN`, `SURVIVED`).

## What was added

| File | Role |
| --- | --- |
| `internal/selfcheck/fmtguard/` | Structured guard: reports `.go` files that `go/format` would change, as `invaris.inspection/v1alpha1`. Modelled on `examples/go-project/tools/importguard`. |
| `selfcheck.guardrail.json` | `invaris.dev/v1alpha4` harness: guard `gofmt` (policy `gofmt-clean`, over `cmd` and `internal`), challenges `trailing-whitespace-detected` and `secret-missed-control`. |
| `selfcheck.mutation-killed.json` | `invaris.dev/v1alpha3`: `after = append(after, '\r')` to `after = append(after, ' ')` in `internal/mutation/operators.go`. |
| `selfcheck.mutation-survived.json` | `invaris.dev/v1alpha3`: `ineligible("empty file")` to `ineligible("empty input")` in the same file. |
| `selfcheck.campaign.json` | Runs the four experiments above with `requireNoSurvivors` and `requireAllGuardrailsProven`. |

The harnesses sit at the repository root because an experiment copies the harness's directory.

Expected outcomes, written before running:

| Run | Expected |
| --- | --- |
| `check selfcheck.guardrail.json` | ACCEPT, exit 0 |
| `challenge selfcheck.guardrail.json` | `trailing-whitespace-detected` PROVEN; `secret-missed-control` UNPROVEN, `guard_passed` (the guard never reads Markdown) |
| `mutate selfcheck.mutation-killed.json` | KILLED, exit 0 |
| `mutate selfcheck.mutation-survived.json` | SURVIVED (`all_tests_passed`), exit 1: tests only check `errors.Is(err, ErrIneligible)`, never the message |
| `campaign selfcheck.campaign.json` | REJECT, exit 1, naming the survivor and the unproven control |

## Preparation

```sh
go test ./internal/selfcheck/...                                   # ok
gofmt -l cmd internal                                              # no output: the tree is gofmt-clean
go run ./internal/selfcheck/fmtguard -policy gofmt-clean cmd internal
# {"version":"invaris.inspection/v1alpha1","policyId":"gofmt-clean","inspected":101,"findings":[]}  exit 0
```

`minInspected` is 50, about half of the real count of 101, so deleting a few files does not trip it but losing the scan does. Each `preimageSha256` is `shasum -a 256` of the target at authoring time. The harness files record those digests. `internal/mutation/operators.go` is pinned by three of the four experiments (the trailing-whitespace challenge and both mutation harnesses) and `docs/releases/0.3.0.md` by the control; if a target changes, every experiment that pins it becomes `INCONCLUSIVE` (`mutation_rejected`) until its digest is updated, so update the digests together with the edit.

## Runs

All binaries came from `go build -o $SC/invaris ./cmd/invaris`. Wall time is `date +%s` before and after, so it has one-second resolution.

### Run 0: from the repository root (failed, setup/environment)

```sh
invaris check selfcheck.guardrail.json                       # exit 0, 1 s, ACCEPT, inspected=101
invaris --report ... challenge --format text selfcheck.guardrail.json
```

`check` passed. `challenge` exited **2**: both challenges `INCONCLUSIVE`, reason `workspace_prepare_failed`, `detail: details withheld`, stage `prepare FAILED`. Nothing about the experiment was evaluated. Cause, found by reading `docs/threat-model.md` and `internal/workspace/workspace.go`: the copier accepts at most 2000 entries and rejects symbolic links, and the checkout contains `adapters/dependency-cruiser/node_modules` (git-ignored, with symlinks under `.bin`). A checkout with `node_modules` installed is about 69 MB; the ignored `node_modules` directory can never be copied, so the experiment runs only from a checkout without it, such as a fresh clone.

Workaround, used for every run below: copy the tree without `.git`, `node_modules` and `dist` into a scratch directory and run Invaris there.

```sh
rsync -a --exclude .git --exclude node_modules --exclude dist --exclude .DS_Store ./ $SC/repo/
```

The copy has 450 entries and 6.2 MB. This is the same source as the checkout, minus ignored directories. The report records `gitRevision: null` for mutation runs in this copy, so it is not tied to a commit by the report itself. Nothing in the real checkout was changed.

### Run 1: guardrail check

```sh
cd $SC/repo && invaris --report sc-check.json check --format text selfcheck.guardrail.json
```

Actual: ACCEPT, **exit 0**, `inspected=101 findings=0`, 1 s. As expected.

### Run 2: guardrail challenge

```sh
invaris --report sc-challenge.json challenge --format text selfcheck.guardrail.json
```

Actual: **exit 1**, decision REJECT, 2 s.

| Challenge | Baseline | Challenged | Verdict | Reason |
| --- | --- | --- | --- | --- |
| `trailing-whitespace-detected` | PASS | FAIL, finding `gofmt-clean` at `internal/mutation/operators.go` | PROVEN | `guard_detected` |
| `secret-missed-control` | PASS | PASS | UNPROVEN | `guard_passed` |

As expected for the verdicts. The exit code is 1, not 0, because the gate requires every challenge to be proven and the control is not; that is the control working, not a defect. The first challenge is the detected outcome. The second is the missed outcome with its reason.

### Run 3: mutation that should be killed

First attempt, with the commands as first written (`program: go`, `args: ["test","-count=1","./internal/mutation"]` and `go vet`): **exit 2**, decision REFUSE, verdict `INCONCLUSIVE`, reason `malformed_evidence`, baseline stage `FAILED`: `invalid character 'o' looking for beginning of value` (that is `ok  github.com/...` printed by `go test`). 0 s. The mutation harness contract requires the test and validation commands to print a JSON result object, so plain `go test` cannot be used. This is a setup error, not a finding about the code. The report was kept as `sc-killed-v1.json`.

Fix: both commands became small `sh -c` adapters inside the harness (no new files). The validation prints the `invaris.validity-result/v1alpha1` object from the exit status of `go vet ./internal/mutation`. The test command runs `go test -count=1 ./internal/mutation` once and reports `PASS` or `ASSERTION_FAILED` for each of `TestPlanGoldens`, `TestPlanIneligibleInputs` and `TestValidate` by looking for `--- FAIL: <name>` in the output; a nonzero exit with no such line exits 2 (infrastructure). `testIds` lists the three tests. The sources of the mutation and the verdict rules were not changed.

Second attempt, `invaris --report sc-killed.json mutate selfcheck.mutation-killed.json`: **exit 0**, ACCEPT, verdict KILLED, reason `assertion_failed`, 2 s. `TestPlanGoldens` ASSERTION_FAILED, the other two PASS. As expected. A separate direct check of the same edit in a scratch copy showed `TestPlanGoldens/crlf_first_LF_only` and `TestPlanGoldens/crlf_leading_empty_line` failing.

### Run 4: mutation that should survive

`invaris --report sc-survived.json mutate selfcheck.mutation-survived.json`: **exit 1**, decision REJECT, verdict SURVIVED, reason `all_tests_passed`, 1 s. All three tests PASS. As expected.

### Run 5: campaign

`invaris --report sc-campaign.json campaign --format text selfcheck.campaign.json`: **exit 1**, decision REJECT, 5 s.

- Mutation score 50.0% (1 of 2 eligible).
- Guardrail proof rate 50.0% (1 of 2 eligible). By operator: `trailing-whitespace@1` 100.0%, `secret-leak-injection@1` 0.0%.
- Reasons: `requireNoSurvivors: VIOLATED (mutation-survived)`; `requireAllGuardrailsProven: VIOLATED (guardrail-missed)`.

As expected. Every outcome matched the expectation once the two setup errors were fixed; none of the verdicts was tuned.

Summary of actual results:

| Command | Exit | Outcome | Wall |
| --- | --- | --- | --- |
| `check` (root) | 0 | ACCEPT | 1 s |
| `challenge` (root) | 2 | `workspace_prepare_failed` (setup, see friction) | 0 s |
| `check` (copy) | 0 | ACCEPT | 1 s |
| `challenge` (copy) | 1 | 1 PROVEN, 1 UNPROVEN | 2 s |
| `mutate` killed, plain `go test` | 2 | `malformed_evidence` (setup) | 0 s |
| `mutate` killed, adapter | 0 | KILLED | 2 s |
| `mutate` survived | 1 | SURVIVED | 1 s |
| `campaign` | 1 | REJECT, score 50%, proof rate 50% | 5 s |

The generated reports are not committed.

## Where help was needed

Two things needed more than the examples: the copy limits (consulting the threat model and the workspace source), and the mutation evaluator contract (consulting `docs/harness-spec.md` and `examples/go-project/tools/goeval`). Neither is hinted at by the error message alone.

## Friction log

Minutes are estimates of observed time from the failing run to a working one, not measurements from a clock.

| # | Stage | Symptom | Minutes lost | What resolved it | Consulted |
| --- | --- | --- | --- | --- | --- |
| 1 | workspace | `challenge` exit 2, `reason=workspace_prepare_failed`, `detail: details withheld`, `stage prepare FAILED: details withheld`. The message does not say what failed to copy. | about 10 | Looked for symlinks and counted entries (`find`), then read the threat model's copy limits and `internal/workspace/workspace.go` (`MaxEntries = 2000`, symlinks rejected). Cause: git-ignored `adapters/dependency-cruiser/node_modules`. Copied the tree without it. | `docs/threat-model.md`, `internal/workspace/workspace.go`, `.gitignore`. I had to guess "node_modules" from `find`; no document says an ignored directory in the checkout can stop the run. |
| 2 | interpretation | `mutate` exit 2, `malformed_evidence: invalid character 'o' looking for beginning of value` on the baseline. The message does not say which command, nor that a JSON result object is required. | about 8 | Read the "Commands and evaluator output" section of the harness spec and the example's `goeval`. Wrote `sh -c` adapters, because plain `go test` cannot be used. | `docs/harness-spec.md`, `examples/go-project/tools/goeval/main.go`, the example README (which mentions `tools/goeval` but not why it exists). |
| 3 | tool discovery | `--report` refuses to overwrite: `report destination ... already exists` (exit 2, before anything ran). A re-run after fixing a setup error needs a new file name. | about 1 | Renamed the earlier report. | Error message was sufficient. |
| 4 | tool discovery | The expected-versus-actual rule for challenge exit codes: a challenge with one UNPROVEN control exits 1 (REJECT), so "expect one PROVEN, one UNPROVEN" does not translate to exit 0. | about 1 | Reasoned from the gate default (all challenges required). | `docs/harness-spec.md` gate semantics. A guess before running; the result confirmed it. |
| 5 | authoring | No trouble with the v1alpha4 harness, built-in operators and fixture, `preimageSha256`, or the campaign file: the examples under `examples/operators` and `examples/go-project` were enough and no field was misspelled. | 0 | | |
| 6 | environment | `GOTOOLCHAIN` resolved the required Go version from cache without trouble in this session; the allowlist includes `GOTOOLCHAIN`, `GOPROXY` and `GOFLAGS` for that reason. No trouble. | 0 | | |

Where I had to read source code rather than documentation: item 1 (`internal/workspace/workspace.go`) and item 2 (`goeval`). Where I guessed: the cause in item 1 (confirmed afterwards by the run succeeding in the reduced copy, not by a message) and the exit code in item 4.

Smaller observations, not counted as friction: `check` and `challenge` print the guard's evidence ID as `gofmt`, which reads like a guard name; the campaign `--format text` output was clear and listed the reasons by experiment ID.

## After the 0.4.0 commands

The same experiment was repeated with `invaris doctor` and `invaris explain`. The failing and clean runs below used the same harnesses, a fresh binary and the copy procedure from Run 0.

### `doctor` on a checkout with `node_modules` installed

```sh
invaris doctor selfcheck.guardrail.json        # exit 1
```

`doctor` loaded the harness, resolved `go` in the PATH its guard would use, confirmed both targets and both pinned edits, and reported the problem that cost about ten minutes in friction item 1, before anything ran:

```
  [FAIL] workspace.copy  harness directory cannot be copied into a workspace: symlink not permitted: adapters/dependency-cruiser/node_modules/.bin/acorn (limits: 2000 entries, 10485760 ... (truncated)
  [warn] env.gofmt.GOTOOLCHAIN  allowlisted variable is not set in this environment
Summary: 11 passed, 1 failed, 3 warnings, 1 skipped
doctor executed no harness commands; results describe setup only.
```

The text output shortens a long message; `--format json` carries it whole. The three warnings are allowlisted variables unset in the current shell, which is harmless here. In the copy without `node_modules`, `doctor` passes all three harnesses (12, 8 and 8 passes, no failure; the mutation harnesses skip the actions they do not support).

### `doctor` and a pinned preimage

Changing one byte of `internal/mutation/operators.go` in the copy made `doctor` fail the pinned edits before any run:

```
  [FAIL] edit.trailing-whitespace-detected  built-in mutation cannot be applied: ineligible mutation target: content does not match the declared preimage digest
  [FAIL] edit.selfcheck-killed  content does not match the declared preimage digest
```

Reverting the byte returned the harnesses to zero failures.

### `explain` on the saved reports

- The failed run at the checkout root (reports `workspace_prepare_failed`, exit 2) now reads as `inconclusive`, with the reason's meaning, a next step that names the three copy limits and `invaris doctor HARNESS`, and the limits `portable-profile`, `incomplete` and `unauthenticated`.
- The clean challenge reads as one `detected` item (`guard_detected`) and one `missed` item (`guard_passed`, with the next step "the guard does not cover this edit... this is not proof the rule is enforced").
- The campaign reads as `detected`, `missed`, `detected`, `missed`, with the same meanings. It makes the score and the proof rate easier to read, but it does not show them: `explain` classifies each experiment, it does not recompute rates.

### Friction items, re-evaluated

| # | Item | Status |
| --- | --- | --- |
| 1 | `workspace_prepare_failed` with details withheld | **Mostly resolved.** `doctor` finds and names the offending path before a run, and `explain` lists the limits and points at `doctor`. The default limit is unchanged, but a harness can now declare a [`workspace` block](../harness-spec.md#workspace-options): here `"exclude": ["adapters/dependency-cruiser/node_modules"]` would keep the ignored directory out of the copy. This self-check has not been re-run with it. |
| 2 | `malformed_evidence` from a plain `go test` | **Partly resolved.** `explain` now says a mutation test or validation command must print a JSON result and points at the harness spec. `doctor` cannot detect it, because that would mean running the command. |
| 3 | `--report` refuses to overwrite | Unchanged; the message was already clear. |
| 4 | Challenge exit code 1 with one missed control | Unchanged; `explain` shows the decision (`REJECT`) but does not explain the exit code. |

### What the new commands do not cover

- `doctor` does not run adapters or any command, so it cannot check what a command prints, whether `go run ./tool` compiles, or whether provider discovery works; `provider.*` checks are reported as skipped.
- `doctor` inspects one harness; run it for each file a campaign names.
- `explain` interprets what a report records. It does not recompute decisions from retained inputs or compare runs.

## Known limits

- gofmt-clean is not a rule the maintainers of this repository assert is critical. It was chosen because the repository already satisfies it, the guard is a small program, and a trailing space is an unambiguous fault. This shows that the workflow runs on this repository, not that this repository's quality gate is strong.
- The survivor is a message-text gap: no test checks the text of the "empty file" message, only that the error wraps `ErrIneligible`. It is a low-value demonstration of a `missed` outcome, not a claim of a serious hole in the tests, and nobody has decided that the message should be tested.
- The control `secret-missed-control` is missed by construction: the gofmt guard never reads Markdown. It demonstrates how a miss is reported, not a weakness in the guard.
- The runs used a copy of the checkout without `.git`, `node_modules` and `dist`, so mutation reports do not carry a git revision.
- The mutation harnesses use shell adapters rather than a Go evaluator; a vet failure of any kind is reported as `INVALID`, and a test run is classified by searching the text for `--- FAIL:`. They suit this experiment and are not a general adapter.
- Wall times have one-second resolution and come from a single run each.
- A second operator has not repeated this workflow, including with `doctor` and `explain`. This is an open item: it still needs doing, by someone, on a different operator or a different project, before any claim that the workflow generalises.
