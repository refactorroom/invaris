package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/akkaraponph/invaris/internal/configfile"
	"github.com/akkaraponph/invaris/internal/doctor"
)

const doctorUsage = "invaris doctor [--format text|json] [HARNESS]"

// doctorFooter is the last line of text output.
const doctorFooter = "doctor executed no harness commands; results describe setup only."

// doctorArgs parses the arguments after doctor: optional flags, then at most
// one harness path (default .invaris/invaris.json, then invaris.json).
func doctorArgs(args []string) (format, file string, explicit bool, err error) {
	format = formatText
	seenFormat := false
	for i := 0; i < len(args); i++ {
		arg := args[i]
		switch {
		case explicit:
			if strings.HasPrefix(arg, "--") {
				return "", "", false, fmt.Errorf("flags must come before the harness file: %s", arg)
			}
			return "", "", false, fmt.Errorf("unexpected argument: %s", arg)
		case arg == "--format":
			if seenFormat {
				return "", "", false, errors.New("--format is repeated")
			}
			seenFormat = true
			if i+1 >= len(args) || args[i+1] == "" {
				return "", "", false, errors.New("--format requires a value")
			}
			i++
			if format = args[i]; format != formatText && format != formatJSON {
				return "", "", false, fmt.Errorf("unsupported format: %s", format)
			}
		case strings.HasPrefix(arg, "--"):
			return "", "", false, fmt.Errorf("unknown flag: %s", arg)
		default:
			file, explicit = arg, true
		}
	}
	if !explicit {
		file = configfile.DefaultPath("invaris.json")
	}
	return format, file, explicit, nil
}

// runDoctorCLI inspects a harness's setup without running harness commands or
// writing files. Exit 0 means no check failed, 1 a check failed, 2 a usage
// problem or an unreadable harness file.
func runDoctorCLI(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	format, file, explicit, err := doctorArgs(args)
	if err != nil {
		fmt.Fprintln(stderr, err)
		fmt.Fprintln(stderr, "usage:", doctorUsage)
		return 2
	}
	if info, err := os.Stat(file); err != nil {
		fmt.Fprintln(stderr, "read harness:", err)
		return 2
	} else if info.IsDir() {
		fmt.Fprintln(stderr, "read harness:", file, "is a directory")
		return 2
	} else if !info.Mode().IsRegular() {
		fmt.Fprintln(stderr, "read harness:", file, "is not a regular file")
		return 2
	}
	f, err := os.Open(file)
	if err != nil {
		fmt.Fprintln(stderr, "read harness:", err)
		return 2
	}
	f.Close()
	d := doctor.Inspect(file)
	addHarnessChecks(ctx, &d, explicit)
	var out []byte
	if format == formatJSON {
		if out, err = d.JSON(); err != nil {
			fmt.Fprintln(stderr, err)
			return 2
		}
	} else {
		out = []byte(doctorText(d))
	}
	if _, err := stdout.Write(out); err != nil {
		fmt.Fprintln(stderr, "write stdout:", err)
		return 2
	}
	if d.Failed() {
		return 1
	}
	return 0
}

func addHarnessChecks(ctx context.Context, d *doctor.Diagnosis, explicit bool) {
	status := doctor.Pass
	reason := "selected the default workspace harness"
	switch {
	case explicit:
		reason = "selected by the explicit harness argument"
	case d.Harness == "invaris.json":
		reason = "selected the root fallback because .invaris/invaris.json is absent"
	default:
		if info, err := os.Stat("invaris.json"); err == nil && info.Mode().IsRegular() {
			status = doctor.Warn
			reason = ".invaris/invaris.json takes precedence over invaris.json. Pass invaris.json explicitly to inspect it."
		}
	}
	d.AddCheck("harness.selection", status, reason)

	switch harnessGitStatus(ctx, d.Harness) {
	case gitTracked:
		d.AddCheck("harness.git", doctor.Pass, "tracked in the Git index")
	case gitIgnored:
		d.AddCheck("harness.git", doctor.Warn, ignoredHarnessAdvice)
	case gitUntracked:
		d.AddCheck("harness.git", doctor.Warn, "untracked by Git. Add and commit the harness if it is project policy.")
	default:
		d.AddCheck("harness.git", doctor.Skipped, "Git status could not be determined. Check that Git is available and the harness is in a working tree.")
	}
}

// doctorText renders a diagnosis for people. Ids and messages are escaped.
func doctorText(d doctor.Diagnosis) string {
	var b strings.Builder
	line := func(format string, args ...any) { fmt.Fprintf(&b, format+"\n", args...) }
	version := "not loaded"
	if d.HarnessVersion != nil {
		version = token(*d.HarnessVersion)
	}
	line("Invaris doctor: %s  (%s)", token(d.Harness), version)
	labels := map[string]string{doctor.Pass: "pass", doctor.Fail: "FAIL", doctor.Warn: "warn", doctor.Skipped: "skip"}
	for _, c := range d.Checks {
		line("  [%s] %s  %s", labels[c.Status], token(c.ID), message(c.Message))
	}
	line("Summary: %d passed, %d failed, %d warnings, %d skipped", d.Summary.Pass, d.Summary.Fail, d.Summary.Warn, d.Summary.Skipped)
	line("%s", doctorFooter)
	return b.String()
}
