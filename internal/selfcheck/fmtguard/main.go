// Command fmtguard is a structured Invaris guard for the repository's own
// self-check experiment: it reports Go files that gofmt would change.
//
//	fmtguard -policy ID ROOT...
//
// It prints one invaris.inspection/v1alpha1 object. Exit 0 means no findings
// and exit 1 means at least one. A file it cannot read or parse exits 2 and
// prints no object, so an unreadable tree is never reported as clean.
// `inspected` counts the .go files formatted; findings are sorted by path.
// A ROOT must be a directory (a symlink to one is followed). All directories
// are scanned; files whose names start with "." are skipped, as with gofmt.
package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"go/format"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type finding struct {
	PolicyID string `json:"policyId"`
	Path     string `json:"path"`
}

type inspection struct {
	Version   string    `json:"version"`
	PolicyID  string    `json:"policyId"`
	Inspected int       `json:"inspected"`
	Findings  []finding `json:"findings"`
}

func scan(policy string, roots []string) (inspection, error) {
	out := inspection{Version: "invaris.inspection/v1alpha1", PolicyID: policy, Findings: []finding{}}
	for _, root := range roots {
		// A root that is not a directory (a file, or a symlink to a file)
		// would otherwise be reported as clean with nothing inspected.
		info, err := os.Stat(root)
		if err != nil {
			return out, err
		}
		if !info.IsDir() {
			return out, fmt.Errorf("%s is not a directory", filepath.ToSlash(root))
		}
		// A trailing separator makes WalkDir descend into a symlinked root.
		walkRoot := root
		if !strings.HasSuffix(walkRoot, string(filepath.Separator)) {
			walkRoot += string(filepath.Separator)
		}
		err = filepath.WalkDir(walkRoot, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				return err
			}
			if d.IsDir() {
				return nil
			}
			if strings.HasPrefix(d.Name(), ".") || !strings.HasSuffix(d.Name(), ".go") {
				return nil
			}
			data, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			formatted, err := format.Source(data)
			if err != nil {
				return fmt.Errorf("%s: %w", filepath.ToSlash(path), err)
			}
			out.Inspected++
			if !bytes.Equal(formatted, data) {
				out.Findings = append(out.Findings, finding{PolicyID: policy, Path: filepath.ToSlash(path)})
			}
			return nil
		})
		if err != nil {
			return out, err
		}
	}
	sort.Slice(out.Findings, func(i, j int) bool { return out.Findings[i].Path < out.Findings[j].Path })
	return out, nil
}

func run(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("fmtguard", flag.ContinueOnError)
	fs.SetOutput(stderr)
	policy := fs.String("policy", "", "policy ID reported in the evidence")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *policy == "" || fs.NArg() == 0 {
		fmt.Fprintln(stderr, "usage: fmtguard -policy ID ROOT...")
		return 2
	}
	res, err := scan(*policy, fs.Args())
	if err != nil {
		fmt.Fprintln(stderr, "fmtguard:", err)
		return 2
	}
	enc, err := json.Marshal(res)
	if err != nil {
		fmt.Fprintln(stderr, "fmtguard:", err)
		return 2
	}
	fmt.Fprintln(stdout, string(enc))
	if len(res.Findings) > 0 {
		return 1
	}
	return 0
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}
