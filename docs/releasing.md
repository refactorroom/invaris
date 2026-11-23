# Prepare and publish a release

See [GitHub releases](https://github.com/refactorroom/invaris/releases) for published versions. Replace the example version with the version you are preparing.

## Build and inspect archives

Use the Go version in `go.mod`, Python 3.11 or later, and Linux or macOS on amd64 or arm64. Run from the repository root:

```sh
python3 scripts/package-release.py v0.5.3 --output dist/v0.5.3
python3 scripts/verify-release.py v0.5.3 dist/v0.5.3
```

The destination must not exist. Packaging refuses to overwrite an earlier build; on failure, inspect the partial output and choose a new destination. `dist/` is ignored by Git. Build from the exact tested release commit with a clean worktree before publication.

The directory contains four `invaris_0.5.3_<os>_<arch>.tar.gz` archives (`linux` and `darwin`, each on `amd64` and `arm64`) and `SHA256SUMS`. Every archive has only `invaris`, `invaris-command-provider`, `LICENSE` and a version-specific `README.md` at its root. Builds disable cgo and stamp `engineVersion` with `v0.5.3`.

Verification checks every archive's SHA-256, exact member list, regular file types and executable permissions. It extracts the native archive into a new folder with a space in its name, then runs the installed CLI and provider, checks the stamped version, reads text and compact output, runs an operator campaign, initializes an empty project and rehearses migration with an exact backup. Other architecture binaries are cross-built and inspected, but are not executed on that runner.

## Publish on GitHub

Prepare the release notes at `docs/releases/X.Y.Z.md` and add the
`## X.Y.Z` changelog section on `dev`. Promote `dev` to `main` through a pull
request and wait for Linux CI on the merge commit. Choose that commit in a clean
checkout when building the archives above.

After verifying the archives, create and push the version tag and publish
the files manually:

```sh
TAG=v0.5.3
ARCHIVES="dist/$TAG"
git tag -a "$TAG" -m "Invaris $TAG"
git push origin "refs/tags/$TAG"
gh release create "$TAG" "$ARCHIVES"/*.tar.gz "$ARCHIVES/SHA256SUMS" \
  --verify-tag --title "Invaris $TAG" --notes-file "docs/releases/${TAG#v}.md"
```

GitHub Actions checks source on Linux. Maintainers run archive verification
on the platforms they have available. GitHub Pages is served from `/docs`
on `dev`. Update that branch once the release links are live.

## Publish on npm

Use Node.js 22.14 or later. Build the npm tarball from the same verified
archives. The package output directory must be new.

```sh
TAG=v0.5.3
ARCHIVES="dist/$TAG"
NPM_DIR="dist/npm-$TAG"
node --test npm/launcher.test.js
python3 scripts/package-npm.py "$TAG" "$ARCHIVES" --output "$NPM_DIR"
python3 scripts/verify-npm.py "$TAG" "$ARCHIVES" "$NPM_DIR/invaris-cli-${TAG#v}.tgz"
```

From an authenticated maintainer session, publish the verified tarball
with `npm publish "./$NPM_DIR/invaris-cli-${TAG#v}.tgz" --access public --ignore-scripts`.
Verify the registry copy with
`npx --yes --package="invaris-cli@${TAG#v}" invaris --version`.
Keep the tag and published files together. If a published version needs a
fix, issue a new patch.

## Compatibility and rollback

Existing harnesses retain their default report versions and exit codes. The new v1alpha4 harness requires a 0.3.0 binary and always emits v1alpha5 evidence; opt-in v1alpha5 reports require consumers that understand that schema. Keep the older input files and report consumers when evaluating an upgrade.

To roll back the CLI, reinstall the v0.2.0 archive into a separate directory and put it first on `PATH`. Use v1alpha1, v1alpha2 or v1alpha3 harnesses with that binary; v1alpha4 harnesses and new flags are unsupported. If a harness was migrated, inspect its `.bak` and restore it manually only after checking for later edits. There is no service or database migration. If a published release is defective, mark it as such and ship a new patch version rather than rewriting the tag or replacing files under the same checksums.
