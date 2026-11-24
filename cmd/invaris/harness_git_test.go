package main

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/akkaraponph/invaris/internal/doctor"
)

const workspaceHarness = ".invaris/invaris.json"

func gitTestCommand(t *testing.T, dir string, args ...string) {
	t.Helper()
	cmd := exec.CommandContext(t.Context(), "git", args...)
	cmd.Dir = dir
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
}

func gitTestRepo(t *testing.T) string {
	t.Helper()
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("Git is not installed")
	}
	dir := t.TempDir()
	t.Setenv("GIT_CONFIG_GLOBAL", os.DevNull)
	t.Setenv("GIT_CONFIG_NOSYSTEM", "1")
	gitTestCommand(t, dir, "init", "-q")
	return dir
}

func runHarnessInit(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := runCLI(t.Context(), append([]string{"init"}, args...), &stdout, &stderr)
	return code, stdout.String(), stderr.String()
}

func doctorWithGitChecks(t *testing.T, wantCode int, args ...string) doctor.Diagnosis {
	t.Helper()
	code, out, stderr := runDoctor(t, append([]string{"--format", "json"}, args...)...)
	if code != wantCode || stderr != "" {
		t.Fatalf("doctor exit %d, stdout %q, stderr %q", code, out, stderr)
	}
	var d doctor.Diagnosis
	if err := json.Unmarshal([]byte(out), &d); err != nil {
		t.Fatalf("decode doctor output: %v\n%s", err, out)
	}
	return d
}

func requireDoctorCheck(t *testing.T, d doctor.Diagnosis, id, status, substring string) {
	t.Helper()
	for _, c := range d.Checks {
		if c.ID == id {
			if c.Status != status || c.Executed || !strings.Contains(c.Message, substring) {
				t.Fatalf("unexpected %s check: %+v", id, c)
			}
			return
		}
	}
	t.Fatalf("missing %s check in %+v", id, d.Checks)
}

func TestHarnessGitIgnoreRules(t *testing.T) {
	for _, tc := range []struct {
		name, rootRules, nestedRules string
		wantIgnored                  bool
	}{
		{name: "ignored directory", rootRules: "/.invaris/\n", wantIgnored: true},
		{
			name: "file negation below an ignored directory", wantIgnored: true,
			rootRules: "/.invaris/\n!/.invaris/invaris.json\n",
		},
		{
			name:      "file negation below a visible directory",
			rootRules: "/.invaris/*\n!/.invaris/invaris.json\n",
		},
		{
			name:      "unignore the directory before the file",
			rootRules: "/.invaris/\n!/.invaris/\n/.invaris/*\n!/.invaris/invaris.json\n",
		},
		{
			name: "nearer ignore rule wins", wantIgnored: true,
			rootRules: "/.invaris/*\n!/.invaris/invaris.json\n", nestedRules: "invaris.json\n",
		},
		{
			name:      "nearer negation wins",
			rootRules: "/.invaris/*\n", nestedRules: "!invaris.json\n",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			repo := gitTestRepo(t)
			mustWrite(t, filepath.Join(repo, ".gitignore"), tc.rootRules)
			if tc.nestedRules != "" {
				if err := os.Mkdir(filepath.Join(repo, ".invaris"), 0o755); err != nil {
					t.Fatal(err)
				}
				mustWrite(t, filepath.Join(repo, ".invaris", ".gitignore"), tc.nestedRules)
			}
			before := treeManifest(t, repo)
			t.Chdir(t.TempDir())
			if tc.wantIgnored {
				code, out, stderr := runHarnessInit(t, "--path", repo, "--dry-run")
				if code != 0 || !json.Valid([]byte(out)) || strings.Contains(stderr, "warning:") {
					t.Fatalf("init dry run exit %d, stdout %q, stderr %q", code, out, stderr)
				}
				sameManifest(t, before, treeManifest(t, repo))
			}
			code, out, stderr := runHarnessInit(t, "--path", repo)
			if code != 0 || !strings.HasPrefix(out, "created ") || strings.Contains(stderr, "warning: Git ignores") != tc.wantIgnored {
				t.Fatalf("init exit %d, stdout %q, stderr %q", code, out, stderr)
			}
			t.Chdir(repo)
			d := doctorWithGitChecks(t, 0)
			requireDoctorCheck(t, d, "harness.selection", doctor.Pass, "default workspace harness")
			wantText := "untracked by Git. Add and commit"
			if tc.wantIgnored {
				wantText = "Unignore the file and any ignored parent directory"
			}
			requireDoctorCheck(t, d, "harness.git", doctor.Warn, wantText)
			code, out, stderr = runDoctor(t)
			if code != 0 || stderr != "" || !strings.Contains(out, "[warn] harness.git") || !strings.Contains(out, wantText) {
				t.Fatalf("doctor exit %d, stdout %q, stderr %q", code, out, stderr)
			}
			after := treeManifest(t, repo)
			delete(after, filepath.FromSlash(workspaceHarness))
			if tc.nestedRules == "" {
				delete(after, ".invaris")
			}
			sameManifest(t, before, after)
		})
	}
}

func TestHarnessGitUsesProjectWorktree(t *testing.T) {
	repo := gitTestRepo(t)
	t.Chdir(repo)
	mustWrite(t, ".gitignore", "/.invaris/\n")
	gitTestCommand(t, repo, "init", "-q", ".invaris")
	code, out, stderr := runHarnessInit(t)
	if code != 0 || !strings.Contains(stderr, "warning: Git ignores") {
		t.Fatalf("init exit %d, stdout %q, stderr %q", code, out, stderr)
	}
	gitTestCommand(t, filepath.Join(repo, ".invaris"), "add", "--", "invaris.json")
	d := doctorWithGitChecks(t, 0)
	requireDoctorCheck(t, d, "harness.git", doctor.Warn, "Git ignores this harness")
}

func TestHarnessGitSelectionAndTracking(t *testing.T) {
	repo := gitTestRepo(t)
	project := filepath.Join(repo, "nested project")
	if err := os.Mkdir(project, 0o755); err != nil {
		t.Fatal(err)
	}
	t.Chdir(project)
	const config = `{"version":"invaris.dev/v1alpha2","name":"example","trustMode":"trusted-local","networkPolicy":"unrestricted"}`
	mustWrite(t, "invaris.json", config)
	gitTestCommand(t, project, "add", "--", "invaris.json")
	mustWrite(t, filepath.Join(repo, ".gitignore"), "/nested project/invaris.json\n/nested project/.invaris/\n")

	d := doctorWithGitChecks(t, 0)
	if d.Harness != "invaris.json" {
		t.Fatalf("expected the root path, got %q", d.Harness)
	}
	requireDoctorCheck(t, d, "harness.selection", doctor.Pass, "root fallback")
	requireDoctorCheck(t, d, "harness.git", doctor.Pass, "tracked in the Git index")

	if err := os.Mkdir(".invaris", 0o755); err != nil {
		t.Fatal(err)
	}
	mustWrite(t, workspaceHarness, "{")
	d = doctorWithGitChecks(t, 1)
	if d.Harness != filepath.FromSlash(workspaceHarness) {
		t.Fatalf("expected the workspace path, got %q", d.Harness)
	}
	requireDoctorCheck(t, d, "harness.selection", doctor.Warn, ".invaris/invaris.json takes precedence over invaris.json")
	requireDoctorCheck(t, d, "harness.git", doctor.Warn, "Git ignores this harness")
	requireDoctorCheck(t, d, "harness.load", doctor.Fail, "")

	mustWrite(t, workspaceHarness, config)
	d = doctorWithGitChecks(t, 0)
	requireDoctorCheck(t, d, "harness.selection", doctor.Warn, "takes precedence")
	d = doctorWithGitChecks(t, 0, "invaris.json")
	if d.Harness != "invaris.json" {
		t.Fatalf("expected the explicit root path, got %q", d.Harness)
	}
	requireDoctorCheck(t, d, "harness.selection", doctor.Pass, "explicit harness argument")
	requireDoctorCheck(t, d, "harness.git", doctor.Pass, "tracked in the Git index")
}

func TestHarnessGitUnknown(t *testing.T) {
	t.Run("outside a repository", func(t *testing.T) {
		dir := t.TempDir()
		t.Setenv("GIT_CEILING_DIRECTORIES", filepath.Dir(dir))
		checkUnknownHarnessGit(t, dir)
	})
	t.Run("Git unavailable", func(t *testing.T) {
		dir := gitTestRepo(t)
		t.Setenv("PATH", t.TempDir())
		checkUnknownHarnessGit(t, dir)
	})
	t.Run("Git error", func(t *testing.T) {
		dir := gitTestRepo(t)
		bin := t.TempDir()
		// Return an empty index result, then fail while checking ignore rules.
		fakeGit := "#!/bin/sh\nfor arg do\n  case \"$arg\" in ls-files) exit 0;; check-ignore) exit 128;; esac\ndone\nexit 128\n"
		if err := os.WriteFile(filepath.Join(bin, "git"), []byte(fakeGit), 0o700); err != nil {
			t.Fatal(err)
		}
		t.Setenv("PATH", bin)
		checkUnknownHarnessGit(t, dir)
	})
}

func checkUnknownHarnessGit(t *testing.T, dir string) {
	t.Helper()
	t.Chdir(dir)
	code, out, stderr := runHarnessInit(t)
	if code != 0 || !strings.HasPrefix(out, "created ") || strings.Contains(stderr, "warning:") {
		t.Fatalf("init exit %d, stdout %q, stderr %q", code, out, stderr)
	}
	d := doctorWithGitChecks(t, 0)
	requireDoctorCheck(t, d, "harness.git", doctor.Skipped, "Git status could not be determined")
}
