# Diagnostics: doctor and explain

Two commands help with the first experiment. `invaris doctor` inspects a harness before a run, and `invaris explain` interprets a report after one. Neither runs a harness command, neither writes a report, and neither is verification evidence, so `--report` is rejected for both. Their output is for people and for scripts that want to read a setup or a result; it carries no decision of its own.

A diagnostic never says that something passed when it was not performed. What `doctor` cannot know without running a command it reports as skipped, and what a report cannot show `explain` lists as a limit.

## doctor: inspect harness setup

```sh
invaris doctor [--format text|json] [harness.json]
```

The default harness is `.invaris/invaris.json`, with `invaris.json` as a fallback when the workspace file is absent. An explicit path selects that file. The default format is `text`. Flags come before the harness path. `doctor` loads the harness with the same strict loader the other commands use. A harness directly inside `.invaris` inspects its parent project directory.

For readable harnesses, `doctor` shows the selected path and explains the selection. If both default files exist, automatic selection warns that the workspace file takes precedence. It checks Git from the same project directory it inspects, using read-only Git queries. Every JSON check has `"executed": false` because `doctor` runs no harness command.

The Git check passes for a file in the Git index, warns if the file is ignored or untracked, and is skipped when Git status could not be determined, for example when Git is missing or the file is outside a checkout. A tracked file may still need to be committed or pushed. Git warnings leave the exit code unchanged. To fix a sharing warning, see [how to share a project harness through Git](authoring.md#share-a-project-harness-through-git).

| Exit | Meaning |
| --- | --- |
| `0` | No check failed. Warnings and skipped checks do not change the exit code. |
| `1` | A setup check failed, including a harness that does not load. This is a setup problem, not a rejected verification. |
| `2` | Usage error, or the harness file cannot be read at all (missing, not a regular file, no permission). |

The text output lists each check as `[pass]`, `[FAIL]`, `[warn]` or `[skip]`, then a summary, then always ends with this line:

```
doctor executed no harness commands; results describe setup only.
```

Text output shortens a long message; `--format json` carries it whole.

### Checks

Checks appear in this order. `<id>` is the ID of the step, guard, challenge or experiment, or `adapter.<id>` for an adapter's command.

| Check ID | Fails or warns when |
| --- | --- |
| `harness.load` | The harness does not load. Then `inspection` is skipped, and doctor still reports selection and Git status. |
| `harness.version` | Warns when a loaded v1alpha1 harness can be previewed for migration to v1alpha2. Migration preserves the existing effective behavior and keeps a backup when written. |
| `action.run`, `action.check`, `action.challenge`, `action.mutate` | Never fails. Skipped when the harness version does not support the action, or, for `challenge`, when it declares none. |
| `workspace.copy` | The harness directory could not be copied into a workspace: a symbolic link, a file over 10 MiB, an unreadable file, a declared dependency that is not a directory, or more entries than the bound (2000, or the harness's `workspace.maxEntries`). The message names the path relative to the harness directory and the [`workspace` field](harness-spec.md#workspace-options) that resolves it. Paths the harness excludes or declares as dependencies are not checked. Checked only when there is a challenge or an experiment, because only those copy the directory; skipped otherwise. |
| `program.<id>` | The command's program is not found. A bare name is searched only in the PATH the command would get: the allowlisted `PATH` when `envAllowlist` names it, otherwise `/usr/bin:/bin`. A relative path that leaves the directory or points into `.git` or `.invaris` warns, because a real run resolves it inside the workspace copy. |
| `env.<id>.<VAR>` | Warns for each allowlisted variable that is not set in the environment `doctor` runs in. Only names are shown, never values. |
| `target.<id>` | The challenge or experiment target does not exist, is not a regular writable file inside the harness directory, or is in `.git` or `.invaris`, which a workspace copy omits. |
| `edit.<id>` | A literal `before` marker does not occur exactly once, a declared `preimageSha256` no longer matches the file, or a built-in operator cannot apply to the file (for example a file with carriage returns). |
| `writable.<path>` | A `writablePaths` entry that an edit targets does not resolve to a regular file (fails), or that nothing uses does not exist (warns). |
| `provider.<id>` | Always skipped: discovering a provider runs its adapter, which `doctor` does not do. |
| `harness.selection` | Warns when both default files exist and automatic discovery selects the workspace file. |
| `harness.git` | Warns when the selected file is ignored or untracked. Skipped when Git status could not be determined. |

A `pass` means the setup that was inspected looks right. It does not mean a command will print the result object its role requires, that `go run ./tool` will compile, or that a guard will find anything.

`doctor` inspects one harness. A campaign file is not a harness: run `doctor` on each harness it names.

### JSON

`--format json` prints [`invaris.doctor/v1alpha1`](../schemas/doctor-v1alpha1.schema.json): `harness`, `harnessVersion` (`null` when it did not load), `checks` (`id`, `status`, `executed`, `message`) and a `summary` of counts by status.

## explain: interpret a saved report

```sh
invaris explain [--format text|json] report.json
```

`explain` reads a report written with `--report` (or redirected from stdout), validates it with the rules that wrote it, and prints what each result means. It reads evidence versions v1alpha2 to v1alpha5 for `run`, `check`, `challenge`, `mutate` and `campaign`. It runs nothing and writes nothing.

| Exit | Meaning |
| --- | --- |
| `0` | The report was explained. This says nothing about the report's own decision. |
| `2` | Usage error, unreadable file, a report that is not valid evidence (including one whose decision was edited), or an unsupported report version. Nothing is interpreted. |

### Classes

Each step, guard, proof, mutation or campaign experiment gets a class that separates what was recorded from what it means for a fault:

| Class | Recorded as |
| --- | --- |
| `detected` | A proof `PROVEN`, or a mutation or experiment `KILLED` or `PROVEN`: the edit was caught. |
| `missed` | A proof `UNPROVEN`, or a mutation or experiment `SURVIVED` or `UNPROVEN`: nothing caught the edit. |
| `inconclusive` | The evidence does not decide: `INCONCLUSIVE`, `MIXED` repeats, or a check that refused. A setup or tool failure is inconclusive, never a miss. |
| `excluded` | A mutant that was `INVALID`, which takes no part in a score. |
| `not-run` | Filtered out, not selected, or never evaluated. |
| `passed`, `failed` | A step or guard `PASS` or `FAIL` in a `run` or `check`. |

When the report recorded a reason, the item shows it with its [category](evidence-schema.md#reasons-and-categories), what it means, and a next step. A reason is shown for a campaign experiment only when every attempt recorded the same one.

### Limits

`limits` list what the report cannot show, in this order and only when they apply:

| Code | Applies when |
| --- | --- |
| `weak-evidence` | A completed proof rests on a text marker or any strength other than `strong`. A weak proof is not structured rule detection. |
| `portable-profile` | The report is v1alpha5, which withholds machine paths, command arguments, output and free text. |
| `legacy-input` | The report came from a v1alpha1 harness. |
| `dirty-worktree` | The working tree had uncommitted or untracked changes, so a Git revision alone does not identify the tested files. |
| `incomplete` | The decision is `REFUSE`: the evidence is incomplete or unsupported. |
| `unauthenticated` | Always. Matching hashes show that bytes are consistent, not who ran the check or how. |

`explain` classifies; it does not recompute scores, replay commands or compare runs. Read the report's own summary for a mutation score and a guardrail proof rate.

### JSON

`--format json` prints [`invaris.explanation/v1alpha1`](../schemas/explanation-v1alpha1.schema.json): `report` (schema version, action, run ID, decision and subject), `items` (`id`, `kind`, `outcome`, `class`, `reason`, `category`, `meaning`, `next`, and optional `details`) and `limits`. `reason`, `category` and `next` are `null` when the report recorded no reason.

`details` quotes what the report recorded behind a mutation that was neither killed nor survived, for `mutate` reports and campaign experiments: each failed stage's detail (unless it only repeats the reason) and each baseline test that did not pass, at most 20 lines plus a count of the rest. Campaign lines start with the attempt number. Text output prints them as `detail:` lines under the reason. For example, a test command whose result lists the whole suite shows `detail: stage baseline: malformed_evidence: test evidence has 41 tests but the harness selects 1 testIds; ...`, and a suite whose selected test fails alone shows `detail: baseline test test/api.e2e-spec.ts::...: ASSERTION_FAILED`. Portable v1alpha5 reports withhold stage details, so fewer lines appear.

## A worked example

The [self-check experiment](experiments/self-check.md) runs both commands on this repository. `doctor` names the installed `node_modules` that a workspace copy would refuse, before any run, and reports a pinned preimage that no longer matches. `explain` turns the saved challenge and campaign reports into one `detected` and one `missed` item, with the missed control's next step.
