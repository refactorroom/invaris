# Create and upgrade harness files

`invaris init` writes a starter harness and `invaris migrate` upgrades a v1alpha1 harness to v1alpha2. Neither command runs project code, guards or package scripts, and neither produces verification evidence, so `--report` is rejected for both. Both exit `0` on success and `2` on any usage, validation or filesystem error, with the message on stderr.

After writing or editing a harness, run [`invaris doctor`](diagnostics.md) to find setup problems before a run.

## Create a harness with init

```sh
invaris init [--path DIR] [--preset generic|go] [--detect] [--dry-run]
```

`--path` selects the project root (default `.`). Its own symbolic link is resolved once; the configuration is always `<root>/.invaris/invaris.json`. Each flag may appear once.

Both presets generate `"version": "invaris.dev/v1alpha2"`. This field identifies the harness format. Run `invaris --version` to see the CLI release. CLI releases can share the same harness format, and updating the CLI leaves existing harness files as they are.

| Form | Effect |
|---|---|
| `invaris init --detect` | Prints marker detection as JSON on stdout. Writes nothing. Cannot be combined with `--preset` or `--dry-run`. |
| `invaris init --dry-run [--preset P]` | Prints the exact configuration on stdout and an explanation on stderr. Writes nothing. |
| `invaris init [--preset P]` | Creates `.invaris/` with mode `0700` if absent and `.invaris/invaris.json` with mode `0600` and prints `created <path>`. It warns on stderr if Git ignores the new harness. |

Detection inspects only these entries at the root, with `lstat`: `go.mod`, `go.work`, `package.json`, `Cargo.toml`, `.gitmodules` and `.git` (directory or file). A marker that is a symbolic link, a special file, unreadable, or larger than 1 MiB is refused. Marker contents are not interpreted, nested directories are not searched, and no tool is invoked. Detection only recommends; it never selects a preset, and mixed or workspace markers are reported as such.

### Workspace layout

Invaris stores new project configuration in `.invaris/invaris.json`. `run`, `check`, `challenge`, `mutate`, `doctor` and `migrate` prefer that file in the current directory and fall back to a root-level `invaris.json` when it is absent. An invalid workspace configuration is reported, never silently skipped. An explicit harness path selects exactly that file.

For a harness directly inside `.invaris`, commands, targets, writable paths and workspace options are relative to its parent project directory. Other harnesses retain their containing directory as the execution root. `.invaris` remains excluded from disposable execution copies, so put guard scripts and other execution inputs in the project itself.

To adopt the layout for an existing project, move `invaris.json` into `.invaris/invaris.json`; project-relative paths keep their meaning. `init` refuses an existing root-level configuration instead of creating a competing one. Existing `.invaris` directories are reused, but a file or symbolic link at `.invaris` is refused. Detection and dry runs create neither the folder nor the file. Verification commands require an existing configuration; use `init` to create it.

### Share a project harness through Git

Normally, commit a harness that defines project policy so teammates and CI receive it in a checkout. You can commit `.invaris/invaris.json` in its default location. Run `invaris doctor` from the project directory to see which harness it selects and how Git classifies it.

If Git ignores the workspace harness, run `git check-ignore -v -- .invaris/invaris.json` from the project directory to locate the matching rule. If a root `.gitignore` excludes `/.invaris/`, replace that rule with these rules to ignore the directory's contents and allow the harness:

```gitignore
/.invaris/*
!/.invaris/invaris.json
```

If you keep the original directory rule, put `!/.invaris/` after it and before the two lines above. Git must be able to enter every parent directory for the file exception to take effect. Use paths relative to the `.gitignore` you edit and check for overriding rules in nearer `.gitignore` files. [Git ignore pattern rules](https://git-scm.com/docs/gitignore#_pattern_format)

Run `invaris doctor` again. Once it reports the harness as untracked, review the harness, stage it with `git add -- .invaris/invaris.json`, and commit it with any shared ignore-rule changes. For a root-level harness, use `invaris.json` in the Git commands. Both `init` and `doctor` leave the ignore rules and Git index as they are.

### Presets

The default `generic` preset is a valid, empty `invaris.dev/v1alpha2` harness:

```json
{
  "version": "invaris.dev/v1alpha2",
  "name": "invaris-project",
  "trustMode": "trusted-local",
  "networkPolicy": "unrestricted",
  "writablePaths": [],
  "policies": [],
  "steps": [],
  "guards": [],
  "challenges": []
}
```

It declares no work, so `invaris check` refuses it with exit `2` until you add guards. No gate is written, so every guard and challenge you add later is required by the [derived gate](harness-spec.md#gate-semantics).

`--preset go` requires a regular `go.mod` at the root and adds one guard, `go-tests`, that runs `go test ./...` with `envAllowlist` `PATH`, `HOME`, `GOCACHE`, `GOMODCACHE` and `GOPATH`. It runs your installed Go toolchain when you run `check`, may download modules at that time, and Invaris does not verify that `go` is on `PATH`. Node.js and Rust are detected but have no preset. No preset adds a challenge, so nothing yet proves that a guard detects a fault; see [challenges](harness-spec.md#challenges).

### No overwrite

`init` never replaces anything at `.invaris/invaris.json`: an existing file (even with identical bytes), directory, symbolic link or dangling link makes it exit `2`. The bytes are staged in a temporary file beside the destination and published with a hard link, which fails if the name was taken in the meantime, so concurrent `init` runs cannot both succeed and no partial file is visible. A filesystem without hard links is refused rather than overwritten.

## Upgrade a v1alpha1 harness with migrate

```sh
invaris migrate [--dry-run] [--from v1alpha1] [--to v1alpha2] [harness.json]
```

The default file is `.invaris/invaris.json`, falling back to `invaris.json` only when the workspace file is absent. The only conversion is `invaris.dev/v1alpha1` to `invaris.dev/v1alpha2`. `--from` must match the file's version and `--to` accepts only `v1alpha2`. A harness that is already v1alpha2 is left byte for byte unchanged (exit `0`, no backup). A v1alpha3 mutation harness is a different contract with no migration path, and unknown versions are refused (exit `2`).

The source and the result are both read with the strict loader. Unknown, duplicate, case-mismatched or null fields make migrate refuse and write nothing; nothing is silently dropped. The conversion:

- sets `version` to v1alpha2 and writes `trustMode: "trusted-local"` and `networkPolicy: "unrestricted"`, which only make the existing trust explicit;
- turns each policy string into `{"id": ..., "allowEmpty": false}`, keeping an omitted `policies` omitted and an empty one empty;
- when `writablePaths` is omitted, lists each challenge `file` once in first-occurrence order (v1alpha1 permitted any challenge target); an explicit list, including an empty one, is kept;
- copies `steps`, `guards` and `challenges` exactly, including literal arguments, environment keys, timeouts and expected output markers, and keeps `failFast` and `alwaysRunGuards`;
- writes the gate v1alpha1 derived: every guard ID and every challenge ID in declaration order, `precedence: "failure-first"` and `allowWeakEvidence: true`, so marker-based proofs keep their v1alpha1 result.

Before writing, migrate compares what `run`, `check` and `challenge` would execute and decide under both files: commands, effective gates, policy declarations, writable targets and scheduling. If it cannot establish that they are equal, it refuses. Formatting changes; behavior does not. Reports from the migrated file say compatibility `native` instead of `legacy`, and the config digest changes.

### Preview and write

`--dry-run` prints the resulting JSON on stdout and the source, target and backup path on stderr. It opens no lock, temporary file or backup.

Without `--dry-run`, the harness must be a regular file (not a symbolic link) with one hard link and owner write permission. Migrate then:

1. creates `<harness>.migrate.lock` exclusively, so cooperating migrations of the same file run one at a time;
2. creates `<harness>.bak` exclusively with the original bytes and mode; an existing backup, even an identical one, stops the migration;
3. writes the new bytes to a temporary file in the same directory with the original mode and syncs it;
4. checks that the harness is still the same file with the same bytes, renames the temporary file over it and syncs the directory;
5. removes the lock.

### Failures and recovery

A failure before the rename leaves the original untouched and removes the backup and temporary file it created. A failure after the rename, such as a directory sync error, exits `2`, says the replacement may have completed, and keeps the backup.

If a migration was killed or the machine lost power, a `.migrate.lock`, `.bak` or `.invaris-migrate-*` file may remain. Migrate never removes a stale lock or restores a backup by itself. To recover:

1. Make sure no migration is running, then run `invaris check` on the harness to see which version loads.
2. Compare the harness with `<harness>.bak`. To undo the migration, review the backup and copy it back over the harness yourself; do not overwrite later edits.
3. Remove the stale lock and any `.invaris-migrate-*` file, and move the backup away before migrating again.

These steps protect against ordinary mistakes and cooperating processes; they do not defend against a hostile process editing the same files.
