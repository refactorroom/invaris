package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func invoke(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var out, errb bytes.Buffer
	code := run(args, &out, &errb)
	return code, out.String(), errb.String()
}

func decode(t *testing.T, s string) inspection {
	t.Helper()
	var res inspection
	if err := json.Unmarshal([]byte(s), &res); err != nil {
		t.Fatalf("stdout %q is not one JSON object: %v", s, err)
	}
	return res
}

func TestCleanFile(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "a.go"), "package a\n\nvar X = 1\n")
	code, out, _ := invoke(t, "-policy", "gofmt-clean", root)
	if code != 0 {
		t.Fatalf("exit %d, want 0", code)
	}
	res := decode(t, out)
	if res.Inspected != 1 || res.PolicyID != "gofmt-clean" || res.Version != "invaris.inspection/v1alpha1" {
		t.Fatalf("unexpected result %+v", res)
	}
	if !bytes.Contains([]byte(out), []byte(`"findings":[]`)) {
		t.Fatalf("findings must be [] not null: %s", out)
	}
}

func TestTrailingWhitespaceIsFinding(t *testing.T) {
	root := t.TempDir()
	bad := filepath.Join(root, "b.go")
	write(t, bad, "package b\n\nvar X = 1 \n")
	code, out, _ := invoke(t, "-policy", "gofmt-clean", root)
	if code != 1 {
		t.Fatalf("exit %d, want 1", code)
	}
	res := decode(t, out)
	if len(res.Findings) != 1 || res.Findings[0].Path != filepath.ToSlash(bad) || res.Findings[0].PolicyID != "gofmt-clean" {
		t.Fatalf("unexpected findings %+v", res.Findings)
	}
}

func TestUnparseableFileExits2WithoutOutput(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "c.go"), "package c\n\nfunc (\n")
	code, out, errb := invoke(t, "-policy", "gofmt-clean", root)
	if code != 2 || out != "" || errb == "" {
		t.Fatalf("code=%d stdout=%q stderr=%q", code, out, errb)
	}
}

func TestUsageErrors(t *testing.T) {
	for _, args := range [][]string{{}, {"-policy", "p"}, {"root"}, {"-nope"}} {
		if code, out, _ := invoke(t, args...); code != 2 || out != "" {
			t.Fatalf("args %v: code=%d stdout=%q", args, code, out)
		}
	}
	if code, out, _ := invoke(t, "-policy", "p", filepath.Join(t.TempDir(), "missing")); code != 2 || out != "" {
		t.Fatalf("missing root: code=%d stdout=%q", code, out)
	}
}

func TestGofmtDirectoryScope(t *testing.T) {
	root := t.TempDir()
	for _, d := range []string{"testdata", "node_modules", "vendor", ".hidden"} {
		write(t, filepath.Join(root, d, "bad.go"), "package x \n")
	}
	write(t, filepath.Join(root, ".ignored.go"), "not Go")
	code, out, errb := invoke(t, "-policy", "gofmt-clean", root)
	if code != 1 {
		t.Fatalf("exit %d, stderr %q", code, errb)
	}
	res := decode(t, out)
	if res.Inspected != 4 || len(res.Findings) != 4 {
		t.Fatalf("unexpected result %+v", res)
	}
}

func TestRootMustBeADirectory(t *testing.T) {
	dir := t.TempDir()
	file := filepath.Join(dir, "a.go")
	write(t, file, "package a\n")
	if code, out, _ := invoke(t, "-policy", "p", file); code != 2 || out != "" {
		t.Fatalf("file root: code=%d stdout=%q", code, out)
	}
	link := filepath.Join(dir, "link.go")
	if err := os.Symlink(file, link); err != nil {
		t.Skip("symlinks unavailable")
	}
	if code, out, _ := invoke(t, "-policy", "p", link); code != 2 || out != "" {
		t.Fatalf("symlink to a file: code=%d stdout=%q", code, out)
	}
}

func TestSymlinkedRootIsFollowed(t *testing.T) {
	dir := t.TempDir()
	write(t, filepath.Join(dir, "real", "bad.go"), "package b \n")
	link := filepath.Join(dir, "link")
	if err := os.Symlink(filepath.Join(dir, "real"), link); err != nil {
		t.Skip("symlinks unavailable")
	}
	code, out, _ := invoke(t, "-policy", "p", link)
	if code != 1 {
		t.Fatalf("exit %d, want 1 (the symlinked directory must be scanned)", code)
	}
	if res := decode(t, out); res.Inspected != 1 || len(res.Findings) != 1 {
		t.Fatalf("unexpected result %+v", res)
	}
}

func TestFindingsSortedAcrossRootsAndNonGoIgnored(t *testing.T) {
	root := t.TempDir()
	write(t, filepath.Join(root, "e", "bad.go"), "package e \n")
	write(t, filepath.Join(root, "d", "z.go"), "package d \n")
	write(t, filepath.Join(root, "d", "notes.txt"), "not go \n")
	code, out, _ := invoke(t, "-policy", "p", filepath.Join(root, "e"), filepath.Join(root, "d"))
	if code != 1 {
		t.Fatalf("exit %d, want 1", code)
	}
	res := decode(t, out)
	if res.Inspected != 2 || len(res.Findings) != 2 || res.Findings[0].Path >= res.Findings[1].Path {
		t.Fatalf("findings must be sorted and non-Go files ignored: %+v", res)
	}
}
