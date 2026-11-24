package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/akkaraponph/invaris/internal/configfile"
	"github.com/akkaraponph/invaris/internal/engine"
)

const initUsage = "invaris init [--path DIR] [--preset generic|go] [--detect] [--dry-run]"

// parsedFlags holds the result of parseFlags: values of valued flags, the
// boolean flags that were present, and positional arguments in order.
type parsedFlags struct {
	values map[string]string
	bools  map[string]bool
	args   []string
}

// parseFlags accepts each listed flag at most once. valued flags need a
// nonempty value; any other argument starting with "-" is an error.
func parseFlags(args []string, valued, boolean []string) (parsedFlags, error) {
	p := parsedFlags{values: map[string]string{}, bools: map[string]bool{}}
	isValued, isBool := map[string]bool{}, map[string]bool{}
	for _, f := range valued {
		isValued[f] = true
	}
	for _, f := range boolean {
		isBool[f] = true
	}
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch {
		case isValued[arg]:
			if _, dup := p.values[arg]; dup {
				return p, fmt.Errorf("%s is repeated", arg)
			}
			if i+1 >= len(args) || args[i+1] == "" {
				return p, fmt.Errorf("%s requires a value", arg)
			}
			i++
			p.values[arg] = args[i]
		case isBool[arg]:
			if p.bools[arg] {
				return p, fmt.Errorf("%s is repeated", arg)
			}
			p.bools[arg] = true
		case strings.HasPrefix(arg, "-"):
			return p, fmt.Errorf("unknown flag: %s", arg)
		default:
			p.args = append(p.args, arg)
		}
	}
	return p, nil
}

// runInitCLI detects project markers or writes a starter harness. It never
// runs project code, never overwrites an existing file and does not produce
// verification evidence.
func runInitCLI(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	usage := func(problem string) int {
		fmt.Fprintln(stderr, problem)
		fmt.Fprintln(stderr, "usage:", initUsage)
		return 2
	}
	f, err := parseFlags(args, []string{"--path", "--preset"}, []string{"--detect", "--dry-run"})
	if err != nil {
		return usage(err.Error())
	}
	if len(f.args) > 0 {
		return usage("unexpected argument: " + f.args[0])
	}
	_, hasPreset := f.values["--preset"]
	if f.bools["--detect"] && (hasPreset || f.bools["--dry-run"]) {
		return usage("--detect inspects only; it cannot be combined with --preset or --dry-run")
	}
	preset := engine.PresetGeneric
	if hasPreset {
		preset = f.values["--preset"]
		if preset != engine.PresetGeneric && preset != engine.PresetGo {
			return usage("unsupported preset: " + preset)
		}
	}
	dir := "."
	if p, ok := f.values["--path"]; ok {
		dir = p
	}
	root, err := canonicalDir(dir)
	if err != nil {
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	detection, err := engine.DetectProject(root)
	if err != nil {
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	if f.bools["--detect"] {
		out := struct {
			Root            string                  `json:"root"`
			Markers         engine.ProjectDetection `json:"markers"`
			Recommendations []string                `json:"recommendations"`
		}{root, detection, detection.Recommendations()}
		data, err := json.MarshalIndent(out, "", "  ")
		if err != nil {
			fmt.Fprintln(stderr, "init:", err)
			return 2
		}
		if _, err := stdout.Write(append(data, '\n')); err != nil {
			fmt.Fprintln(stderr, "write stdout:", err)
			return 2
		}
		return 0
	}
	data, err := engine.RenderInitialConfig(preset, detection)
	if err != nil {
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	target := filepath.Join(root, configfile.WorkspaceDir, "invaris.json")
	explain := "The JSON version identifies the harness format. Use `invaris --version` to check the CLI release.\n" +
		initExplanation(preset)
	if f.bools["--dry-run"] {
		fmt.Fprintf(stderr, "dry run: would create %s (nothing was written)\n%s", target, explain)
		if _, err := stdout.Write(data); err != nil {
			fmt.Fprintln(stderr, "write stdout:", err)
			return 2
		}
		return 0
	}
	// Refuse legacy configurations too, avoiding two competing defaults.
	legacy := filepath.Join(root, "invaris.json")
	if _, err := os.Lstat(legacy); err == nil {
		fmt.Fprintf(stderr, "init: %s already exists; move it to .invaris/invaris.json to adopt the workspace layout\n", legacy)
		return 2
	} else if !errors.Is(err, os.ErrNotExist) {
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	workspace := filepath.Dir(target)
	if err := os.Mkdir(workspace, 0o700); err != nil && !errors.Is(err, os.ErrExist) {
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	// Do not follow an existing workspace symlink to write outside the project.
	if info, err := os.Lstat(workspace); err != nil || !info.IsDir() {
		fmt.Fprintln(stderr, "init: .invaris must be a real directory")
		return 2
	}
	if err := configfile.Create(target, data, 0o600); err != nil {
		if errors.Is(err, configfile.ErrExists) {
			fmt.Fprintf(stderr, "init: %s already exists; init never replaces a configuration (edit it, or use `invaris migrate` for v1alpha1)\n", target)
			return 2
		}
		fmt.Fprintln(stderr, "init:", err)
		return 2
	}
	fmt.Fprintf(stdout, "created %s\n", target)
	fmt.Fprint(stderr, explain)
	if harnessGitStatus(ctx, target) == gitIgnored {
		fmt.Fprintln(stderr, "warning:", ignoredHarnessAdvice)
	}
	return 0
}

// canonicalDir resolves dir's own symbolic links once and requires a directory.
func canonicalDir(dir string) (string, error) {
	abs, err := filepath.Abs(dir)
	if err != nil {
		return "", err
	}
	root, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return "", fmt.Errorf("project root: %w", err)
	}
	info, err := os.Stat(root)
	if err != nil {
		return "", fmt.Errorf("project root: %w", err)
	}
	if !info.IsDir() {
		return "", errors.New("project root " + root + " is not a directory")
	}
	return root, nil
}

func initExplanation(preset string) string {
	if preset == engine.PresetGo {
		return "preset go: one guard runs `go test ./...` with the installed Go toolchain when you run check.\n" +
			"  It may download modules when it runs; Invaris did not verify that go is on PATH.\n" +
			"  No challenges are configured, so nothing yet proves the guard detects a fault.\n"
	}
	return "preset generic: the configuration is valid but declares no guards.\n" +
		"  `invaris check` refuses (exit 2) until you add guards; add challenges to prove they detect faults.\n"
}
