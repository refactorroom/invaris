package main

import (
	"context"
	"errors"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/akkaraponph/invaris/internal/configfile"
)

const (
	gitTracked   = "tracked"
	gitIgnored   = "ignored"
	gitUntracked = "untracked"
	gitUnknown   = "unknown"

	ignoredHarnessAdvice = "Git ignores this harness, so commits and CI may miss it. " +
		"Unignore the file and any ignored parent directory, then add and commit it if it is project policy."
)

// harnessGitStatus asks Git about the file from the project directory,
// which also works for projects nested inside a larger worktree.
func harnessGitStatus(ctx context.Context, file string) string {
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	dir := configfile.ProjectRoot(file)
	rel, err := filepath.Rel(dir, file)
	if err != nil {
		return gitUnknown
	}
	// The ./ prefix protects names that start with pathspec magic. Use Git's
	// slash separator regardless of the host's filepath separator.
	name := filepath.ToSlash(rel)
	path := "./" + name
	git := func(args ...string) *exec.Cmd {
		cmd := exec.CommandContext(ctx, "git", append([]string{"--no-optional-locks", "-c", "core.fsmonitor=false"}, args...)...)
		cmd.Dir = dir
		return cmd
	}
	indexed, err := git("--literal-pathspecs", "ls-files", "-z", "--", path).Output()
	if err != nil {
		return gitUnknown
	}
	for entry := range strings.SplitSeq(string(indexed), "\x00") {
		if entry == name {
			return gitTracked
		}
	}

	err = git("check-ignore", "-q", "--", path).Run()
	var exit *exec.ExitError
	switch {
	case err == nil:
		return gitIgnored
	case errors.As(err, &exit) && exit.ExitCode() == 1:
		return gitUntracked
	default:
		return gitUnknown
	}
}
