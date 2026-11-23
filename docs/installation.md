# Install Invaris and run it from a terminal

The [v0.5.1 release](https://github.com/refactorroom/invaris/releases/tag/v0.5.1) provides Linux and macOS binaries. You do not need Go to use them. You need a terminal, the [GitHub CLI](https://cli.github.com/) (`gh`), `tar`, and a SHA-256 checker. Copying the examples also requires Git. On Windows, use [WSL](#windows-cmd-and-powershell-through-wsl); no native Windows archive is published for this release.

The archive commands below install [v0.5.1](https://github.com/refactorroom/invaris/releases/tag/v0.5.1).

## npm installation after publication

The published [`invaris-cli` npm package](https://www.npmjs.com/package/invaris-cli) requires Node.js 22.14 or later and npm, on Linux or macOS with x64 or arm64; on Windows use WSL. The package includes both the CLI and command provider and does not download binaries during installation. No Go installation is needed.

Run the latest published version in a project with a harness:

```sh
npx --package=invaris-cli@latest invaris check
```

For a project dependency, run the following in the project directory to install or update it:

```sh
npm install --save-dev invaris-cli@latest
npx invaris check
```

For a global installation or update:

```sh
npm install --global invaris-cli@latest
invaris check
```

`@latest` requests the latest npm release. npm manages updates; there is no `invaris update` action. To return to an earlier npm version, install that version explicitly (for example, `npm install --save-dev invaris-cli@X.Y.Z`, replacing `X.Y.Z` with a published version). npm updates do not replace separate archive installations. The provider is included and available to the CLI; harnesses must still allowlist `PATH` when required, as described below.

## Install into a specific folder

These commands work in Bash or Zsh. Choose an absolute installation path and the archive matching your system:

| System | Archive |
| --- | --- |
| macOS, Apple Silicon | `invaris_0.5.1_darwin_arm64.tar.gz` |
| macOS, Intel | `invaris_0.5.1_darwin_amd64.tar.gz` |
| Linux or WSL, x86-64 | `invaris_0.5.1_linux_amd64.tar.gz` |
| Linux or WSL, ARM64 | `invaris_0.5.1_linux_arm64.tar.gz` |

For example, install on macOS Apple Silicon into `$HOME/.local/share/invaris`. Change the first two values for another folder or system. Use a new folder for the first installation; extraction replaces files with matching names.

```sh
INVARIS_HOME="$HOME/.local/share/invaris"
INVARIS_ARCHIVE="invaris_0.5.1_darwin_arm64.tar.gz"
mkdir -p "$INVARIS_HOME"
gh release download v0.5.1 --repo refactorroom/invaris --pattern "$INVARIS_ARCHIVE" --pattern SHA256SUMS --dir "$INVARIS_HOME"
cd "$INVARIS_HOME"
```

Verify the checksum and extract only if it passes. On macOS:

```sh
shasum -a 256 -c --ignore-missing SHA256SUMS && tar -xzf "$INVARIS_ARCHIVE"
```

On Linux or WSL:

```sh
sha256sum --check --ignore-missing SHA256SUMS && tar -xzf "$INVARIS_ARCHIVE"
```

Stop if the download or verification fails. Keep both extracted executables, `invaris` and `invaris-command-provider`, in the installation folder. The latter is needed by harnesses that use the generic command provider. The archive does not include example harnesses or install external analyzers.

## Run from Bash or Zsh

Add the installation folder to your current terminal session:

```sh
export PATH="$INVARIS_HOME:$PATH"
command -v invaris
invaris --version
```

`command -v invaris` should show the installation path, and `invaris --version` prints the installed release, for example `invaris v0.5.1`. `invaris --help` prints usage and exits 0; running `invaris` without an action prints the same usage and exits with status 2.

For future terminals, add the following line once to `~/.bashrc` for Bash or `~/.zshrc` for Zsh, changing the path if necessary:

```sh
export PATH="$HOME/.local/share/invaris:$PATH"
```

Open a new terminal, or run `source ~/.bashrc` (Bash) or `source ~/.zshrc` (Zsh). A macOS login Bash reads `~/.bash_profile`; if that file does not already load `~/.bashrc`, add `source ~/.bashrc` there. Keep the installation folder in place.

You can also invoke the CLI by its full path without configuring PATH:

```sh
"$HOME/.local/share/invaris/invaris" check "$HOME/projects/invaris-demo/invaris.json"
```

Create the demo below before running that command.

## Put example files in a specific project folder

This copies the structured example into a new demo folder you choose. Run in Bash or Zsh after setting PATH above. Choose new checkout and project paths; `git clone` requires an absent or empty destination, and `cp` can replace matching files in an existing project folder.

```sh
INVARIS_SOURCE="$HOME/invaris-source"
INVARIS_PROJECT="$HOME/projects/invaris-demo"
git clone --branch v0.5.1 --depth 1 https://github.com/refactorroom/invaris.git "$INVARIS_SOURCE"
mkdir -p "$INVARIS_PROJECT"
cp "$INVARIS_SOURCE/examples/structured/invaris.json" "$INVARIS_SOURCE/examples/structured/guard.sh" "$INVARIS_SOURCE/examples/structured/source.txt" "$INVARIS_PROJECT/"
cd "$INVARIS_PROJECT"
invaris check
invaris challenge
invaris challenge --format text
invaris --report report.json check
```

`check` runs the guard against `source.txt`. `challenge` reports `PROVEN` after detecting the controlled mutation in a disposable copy. Both return JSON reports and exit 0 on success; `--format text` prints a readable summary with the same exit code. The last command also saves the report to `report.json`; use a new filename each time because existing reports are never overwritten.

For an existing project, run `invaris init --detect` to see which project markers Invaris recognizes, then `invaris init` (or `invaris init --preset go` for a Go module) to create `.invaris/invaris.json` without running project code. Add trusted commands that check your project. The demo guard checks only its sample file. A harness can explicitly invoke a shell. See the [harness specification](harness-spec.md).

Run `invaris doctor` to confirm which harness Invaris selects and whether Git tracks or ignores it. Normally, commit a harness that defines project policy so teammates and CI can use it. The default `.invaris/invaris.json` can be committed in place, and an existing root-level `invaris.json` remains supported. See [how to share a project harness through Git](authoring.md#share-a-project-harness-through-git).

You can select a harness by absolute path from any directory:

```sh
invaris check "$INVARIS_PROJECT/invaris.json"
```

The harness's containing folder is the workspace root. A relative `--report` destination is resolved from the terminal's current directory.

Custom tools and providers installed outside `/usr/bin:/bin` need `"envAllowlist": ["PATH"]` on the relevant command or adapter, or an absolute executable path. Allowlist `PATH` separately for child commands that need your terminal's search path. Provider dependencies may need their own allowlists; see the [adapter protocol](adapter-protocol.md#the-generic-command-provider).

## Run a campaign

The Go example campaign runs the Go toolchain, so it also needs the Go version in the example's `go.mod` (1.22 or later). Using the source checkout from the previous section:

```sh
cd "$INVARIS_SOURCE/examples/go-project"
invaris campaign --format text campaign-accept.json
```

The command prints a summary that ends with `Acceptance: ACCEPT` and exits 0. See [Campaigns](campaigns.md) for the other example campaigns and their exit codes.

## Windows CMD and PowerShell through WSL

Use an installed WSL Linux distribution. From CMD or PowerShell, enter it:

```bat
wsl
```

Inside WSL, follow the Linux installation commands above with the archive matching the distribution's architecture, then copy the demo. Install the prerequisites inside WSL as well. Keep the demo in the Linux filesystem, such as `/home/yourname/projects/invaris-demo`, for the documented POSIX fixtures.

After setup, you can invoke the Linux executable directly from CMD or PowerShell. Replace `yourname` with your WSL username and adjust the paths if you chose other folders:

```bat
wsl --exec /home/yourname/.local/share/invaris/invaris check /home/yourname/projects/invaris-demo/invaris.json
wsl --exec /home/yourname/.local/share/invaris/invaris challenge /home/yourname/projects/invaris-demo/invaris.json
wsl --exec /home/yourname/.local/share/invaris/invaris --report /home/yourname/projects/invaris-demo/report-from-cmd.json check /home/yourname/projects/invaris-demo/invaris.json
```

These commands use absolute Linux paths and do not depend on an interactive shell loading PATH settings. Quote any path containing spaces. Linux and macOS are the tested release platforms; these commands run the Linux CLI in WSL, not a native Windows executable.
