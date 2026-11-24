# Invaris CLI

Invaris runs project checks defined in a JSON harness and tests whether those checks detect deliberate changes. Use guard challenges to test a policy check, mutations to test selected tests, and campaigns to evaluate multiple experiments together. Each run produces evidence for review.

## Requirements

Node.js 22.14 or later and npm on Linux or macOS, x64 or arm64. On Windows, use WSL. The package includes the CLI and command provider; it does not download binaries during installation and does not require Go. Commands configured in your harness may have their own dependencies.

## Install

In a project:

```sh
npm install --save-dev invaris-cli@0.5.2
npx invaris --version
```

Or install globally with `npm install --global invaris-cli@0.5.2` and invoke `invaris` directly. Use `@latest` when you want npm's latest published version. See the [installation guide](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/installation.md) for archives, updates, and WSL instructions.

## Set up checks

From your project directory:

```sh
npx invaris init --dry-run
npx invaris init
npx invaris doctor
```

The dry run previews the configuration. `init` creates `.invaris/invaris.json`. The generic preset has no guards, so `check` refuses until you add checks appropriate for your project. After editing the harness, run:

```sh
npx invaris check --format text
npx invaris --report invaris-report.json check
```

Use a new report path: `--report` writes JSON to a new file. The harness `version` identifies its format, independently of the CLI release version. See [authoring a harness](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/authoring.md) and the [harness specification](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/harness-spec.md).

## Test your checks

- `check` runs the configured guards; `run` runs configured steps and guards.
- `challenge` tests a guard against a configured deliberate violation.
- `mutate` tests whether selected tests detect a configured code change.
- `campaign` runs configured experiments and evaluates their combined results.
- `doctor` inspects setup; `explain` interprets a saved report.

These actions require appropriate configured harnesses or campaign files. A passing baseline alone does not prove that a check detects regressions. See the [examples](https://github.com/refactorroom/invaris/tree/v0.5.2/examples), [campaign guide](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/campaigns.md), and [evidence reference](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/evidence-schema.md).

## Trust and safety

Run only trusted harnesses and tools. Their commands run with your user permissions and can access external files and the network; disposable workspaces are not sandboxes. See the [threat model](https://github.com/refactorroom/invaris/blob/v0.5.2/docs/threat-model.md).

[Project documentation](https://refactorroom.github.io/invaris/) · [GitHub](https://github.com/refactorroom/invaris) · [Releases](https://github.com/refactorroom/invaris/releases)
