#!/usr/bin/env python3
"""Validate the published JSON Schemas against real CLI output.

Builds the CLI into a temporary directory, runs it on the shipped examples and
on temporary harnesses, checks the exit codes, validates every emitted report
against its evidence schema (v1alpha2, v1alpha3 for mutate, v1alpha4 for
campaign, v1alpha5 for v1alpha4 harnesses and --evidence-version v1alpha5),
reads saved reports back through `explain` and inspects the example harnesses with
`doctor`, validating both outputs against their schemas,
validates the example harnesses and campaigns against their input schemas, and
requires deliberate counterexamples to be rejected.

Requires the pinned validator: pip install -r scripts/requirements-schema.txt
Exit status: 0 all checks passed, 1 a check failed, 2 the environment is unusable.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("jsonschema is not installed; run: pip install -r scripts/requirements-schema.txt", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
failures = []
checks = 0


def check(condition, label):
    global checks
    checks += 1
    if not condition:
        failures.append(label)
        print("FAIL", label)


def load(name):
    return json.loads((ROOT / "schemas" / name).read_text())


def validator(schema):
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


evidence_schema, harness_schema = load("evidence-v1alpha2.schema.json"), load("harness-v1alpha2.schema.json")
evidence, harness = validator(evidence_schema), validator(harness_schema)


def valid(v, doc):
    return v.is_valid(doc)


def run_cli(binary, cwd, *args, path_prefix=None):
    # A clean environment: the CLI must not depend on the caller's variables.
    path = os.environ.get("PATH", "/usr/bin:/bin")
    if path_prefix:
        path = str(path_prefix) + os.pathsep + path
    env = {"PATH": path, "HOME": str(cwd)}
    p = subprocess.run([str(binary), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def adapter_checks():
    """Golden responses, the Python example's real output, and counterexamples."""
    schema = load("adapter-v1alpha1.schema.json")
    v = validator(schema)
    data = ROOT / "internal" / "adapter" / "testdata"
    golden = {n: json.loads((data / n).read_text().replace("$ID", "req-1")) for n in ("discover.json", "clean.json", "violation.json")}
    for name, doc in golden.items():
        check(valid(v, doc), f"adapter golden {name} violates schema")
    request = {"version": "invaris.adapter/v1alpha1", "requestId": "r", "operation": "check", "policyIds": ["p"], "scope": ["src", "."]}
    check(valid(v, request), "adapter request should satisfy schema")

    # The independent Python provider's real stdout must satisfy the schema.
    example = ROOT / "adapters" / "example" / "main.py"
    with tempfile.TemporaryDirectory(prefix="invaris-adapter-") as tmp:
        (Path(tmp) / "src").mkdir()
        (Path(tmp) / "src" / "a.txt").write_text("ok")
        for label, req in (
            ("discover", {**request, "operation": "discover", "policyIds": [], "scope": []}),
            ("clean check", {**request, "policyIds": ["no-forbidden-marker"], "scope": ["src"]}),
            ("unsupported mutate", {**request, "operation": "mutate", "policyIds": ["no-forbidden-marker"], "scope": ["src"]}),
        ):
            p = subprocess.run([sys.executable, str(example)], input=json.dumps(req), cwd=tmp, capture_output=True, text=True, timeout=30)
            check(p.returncode == 0, f"example provider {label}: exit {p.returncode}")
            try:
                doc = json.loads(p.stdout)
            except ValueError:
                check(False, f"example provider {label}: stdout is not JSON")
                continue
            check(valid(v, doc) and doc.get("requestId") == "r", f"example provider {label}: response violates schema")

    def mutated(base, edit):
        doc = copy.deepcopy(base)
        edit(doc)
        return doc

    clean, violation = golden["clean.json"], golden["violation.json"]
    negatives = {
        "wrong version": (clean, lambda d: d.update(version="invaris.adapter/v2")),
        "missing provider": (clean, lambda d: d.pop("provider")),
        "blank provider name": (clean, lambda d: d["provider"].update(name=" ")),
        "unknown field": (clean, lambda d: d.update(extra=1)),
        "unknown nested field": (clean, lambda d: d["check"].update(extra=1)),
        "no payload": (clean, lambda d: d.pop("check")),
        "two payloads": (clean, lambda d: d.update(error={"code": "INVALID_REQUEST", "message": ""})),
        "unknown error code": (clean, lambda d: (d.pop("check"), d.update(error={"code": "WEIRD", "message": ""}))),
        "PASS with zero targets": (clean, lambda d: d["check"].update(inspected=0)),
        "PASS with exit 1": (clean, lambda d: d["check"].update(exitCode=1)),
        "PASS with crash exit": (clean, lambda d: d["check"].update(exitCode=127)),
        "PASS with a finding": (violation, lambda d: d["check"].update(status="PASS", exitCode=0)),
        "FAIL with exit 0": (violation, lambda d: d["check"].update(exitCode=0)),
        "FAIL without findings": (violation, lambda d: d["check"].update(findings=[])),
        "NOT_RUN from provider": (clean, lambda d: d["check"].update(status="NOT_RUN")),
        "REFUSE without diagnostics": (clean, lambda d: d["check"].update(status="REFUSE")),
        "absolute finding path": (violation, lambda d: d["check"]["findings"][0].update(path="/etc/passwd")),
        "escaping finding path": (violation, lambda d: d["check"]["findings"][0].update(path="a/../b")),
        "finding without rule": (violation, lambda d: d["check"]["findings"][0].update(ruleId="")),
        "unknown operation capability": (golden["discover.json"], lambda d: d["capabilities"].update(operations=["explode"])),
        "missing capability list": (golden["discover.json"], lambda d: d["capabilities"].pop("prerequisites")),
        "request: unknown operation": (request, lambda d: d.update(operation="explode")),
        "request: check without policies": (request, lambda d: d.update(policyIds=[])),
        "request: check without scope": (request, lambda d: d.update(scope=[])),
        "request: escaping scope": (request, lambda d: d.update(scope=["../x"])),
        "request: absolute scope": (request, lambda d: d.update(scope=["/x"])),
        "request: unknown field": (request, lambda d: d.update(extra=1)),
    }
    for label, (base, edit) in negatives.items():
        check(not valid(v, mutated(base, edit)), f"adapter counterexample accepted: {label}")


def mutation_checks(binary):
    """Validate the shipped mutation harnesses and actual CLI evidence."""
    hv = validator(load("harness-v1alpha3.schema.json"))
    ev = validator(load("evidence-v1alpha3.schema.json"))
    directory = ROOT / "examples" / "mutation"
    for name, expected_exit in (("killed", 0), ("survived", 1), ("invalid", 2), ("deleted", 0)):
        path = directory / f"{name}.json"
        config = json.loads(path.read_text())
        check(valid(hv, config), f"invalid mutation harness: {name}")
        check(not valid(harness, config), f"v1alpha2 accepts mutation harness: {name}")
        code, stdout, stderr = run_cli(binary, ROOT, "mutate", str(path))
        check(code == expected_exit, f"mutate {name}: exit {code}: {stderr}")
        try:
            doc = json.loads(stdout)
        except ValueError:
            check(False, f"mutate {name}: stdout is not JSON")
            continue
        check(valid(ev, doc), f"invalid mutation evidence: {name}")
        check(not valid(evidence, doc), f"v1alpha2 accepts mutation evidence: {name}")
        want_verdict = "KILLED" if name == "deleted" else name.upper()
        check(doc.get("experiment", {}).get("verdict") == want_verdict, f"wrong mutation verdict: {name}")
        for description, edit in {
            "missing test IDs": lambda d: d["experiment"].pop("testIds"),
            "null validation": lambda d: d["experiment"].update(validation=None),
            "bad operator": lambda d: d["experiment"]["mutation"].update(operator="patch"),
            "unsafe target": lambda d: d["experiment"]["mutation"].update(path="../source"),
            "empty write scope": lambda d: d.update(writablePaths=[]),
            "delete with after": lambda d: d["experiment"]["mutation"].update(operator="delete", after="x"),
            "replace without after": lambda d: (d["experiment"]["mutation"].update(operator="replace"), d["experiment"]["mutation"].pop("after", None)),
        }.items():
            bad = copy.deepcopy(config)
            edit(bad)
            check(not valid(hv, bad), f"mutation harness accepted {description}")
        for description, edit in {
            "missing baseline": lambda d: d["experiment"].update(baseline=None),
            "missing mutation": lambda d: d["experiment"].update(mutation=None),
            "missing cleanup": lambda d: d["experiment"]["stages"].pop(),
            "failed cleanup": lambda d: d["experiment"]["stages"][-1].update(status="FAILED"),
            "decision mismatch": lambda d: d.update(decision="ACCEPT" if d["decision"] != "ACCEPT" else "REFUSE"),
        }.items():
            bad = copy.deepcopy(doc)
            edit(bad)
            check(not valid(ev, bad), f"mutation evidence accepted {description}")


def campaign_checks(binary, provider_dir):
    """Validate the shipped campaigns and actual campaign evidence."""
    cv = validator(load("campaign-v1alpha1.schema.json"))
    ev = validator(load("evidence-v1alpha4.schema.json"))
    older = [validator(load("evidence-v1alpha2.schema.json")), validator(load("evidence-v1alpha3.schema.json"))]
    ex = ROOT / "examples"
    files = [ex / "mutation" / "campaign.json", ex / "forbidden-dependency" / "campaign.json",
             ex / "go-project" / "campaign.json", ex / "go-project" / "campaign-accept.json", ex / "go-project" / "campaign-mixed.json"]
    for path in files:
        check(valid(cv, json.loads(path.read_text())), f"campaign violates schema: {path.relative_to(ROOT)}")
    nested = json.loads(files[0].read_text())
    nested["experiments"][0]["harness"] = "services/api/killed.json"
    check(valid(cv, nested), "campaign schema rejects a harness in a subdirectory")
    base = json.loads(files[0].read_text())

    def mutated(edit):
        doc = copy.deepcopy(base)
        edit(doc)
        return doc

    for label, edit in {
        "repeat 0": lambda d: d["experiments"][0].update(repeat=0),
        "repeat 6": lambda d: d["experiments"][0].update(repeat=6),
        "harness escaping the directory": lambda d: d["experiments"][0].update(harness="../b.json"),
        "harness with a dot segment": lambda d: d["experiments"][0].update(harness="a/./b.json"),
        "harness in .git": lambda d: d["experiments"][0].update(harness=".git/b.json"),
        "harness parent": lambda d: d["experiments"][0].update(harness=".."),
        "tool without program": lambda d: d.update(tools=[{"id": "go"}]),
        "tool timeout 301": lambda d: d.update(tools=[{"id": "go", "program": "go", "timeoutSeconds": 301}]),
        "unknown field": lambda d: d.update(parallel=True),
        "unknown experiment field": lambda d: d["experiments"][0].update(timeoutSeconds=5),
        "missing acceptance": lambda d: d.pop("acceptance"),
        "missing required requirement": lambda d: d["acceptance"].pop("requireNoMixed"),
        "mutation with challengeId": lambda d: d["experiments"][0].update(challengeId="c"),
        "guardrail with experimentId": lambda d: d["experiments"][0].update(kind="guardrail"),
        "unknown kind": lambda d: d["experiments"][0].update(kind="fuzz"),
        "wrong version": lambda d: d.update(version="invaris.campaign/v1alpha2"),
        "restricted network": lambda d: d.update(networkPolicy="none"),
        "empty campaign": lambda d: d.update(experiments=[]),
        "score above one": lambda d: d["acceptance"].update(minMutationScore=1.5),
        "null name": lambda d: d.update(name=None),
    }.items():
        check(not valid(cv, mutated(edit)), f"campaign counterexample accepted: {label}")

    reports = {}
    for label, path, want_exit, want_decision, prefix in (
        ("mutation campaign", files[0], 1, "REJECT", None),
        ("forbidden-dependency campaign", files[1], 0, "ACCEPT", provider_dir),
    ):
        code, out, err = run_cli(binary, path.parent, "campaign", path.name, path_prefix=prefix)
        check(code == want_exit, f"{label}: exit {code}, want {want_exit} ({err.strip()})")
        try:
            doc = json.loads(out)
        except ValueError:
            check(False, f"{label}: stdout is not JSON")
            continue
        errors = sorted(ev.iter_errors(doc), key=lambda e: list(e.path))
        check(not errors, f"{label}: report violates schema: {errors[0].message if errors else ''}")
        check(doc.get("decision") == want_decision, f"{label}: decision {doc.get('decision')}")
        for v in older:
            check(not valid(v, doc), f"{label}: an older evidence schema accepts a campaign report")
        reports[label] = doc
    # Without the provider on PATH the campaign is refused before any attempt.
    code, out, _ = run_cli(binary, files[1].parent, "campaign", files[1].name)
    try:
        doc = json.loads(out)
        check(code == 2 and valid(ev, doc) and doc["experiments"][0]["attempts"][0]["execution"] == "NOT_STARTED",
              "missing provider: expected a valid REFUSE report with NOT_STARTED attempts")
    except (ValueError, KeyError, IndexError):
        check(False, "missing provider: no campaign report")
    code, out, err = run_cli(binary, files[0].parent, "campaign", "--only", "absent", files[0].name)
    check(code == 2 and out == "" and err.strip() != "", "unknown --only must exit 2 with no stdout")

    doc = reports.get("mutation campaign")
    if doc is None:
        check(False, "no campaign report to derive counterexamples from")
        return
    for key in load("evidence-v1alpha4.schema.json")["required"]:
        check(not valid(ev, {k: v for k, v in doc.items() if k != key}), f"campaign evidence missing {key} accepted")
    for label, edit in {
        "unknown top-level field": lambda d: d.update(extra=1),
        "unknown execution": lambda d: d["experiments"][0]["attempts"][0].update(execution="SKIPPED"),
        "unknown stability": lambda d: d["experiments"][0].update(stability="STABLE"),
        "unknown selection": lambda d: d["experiments"][0].update(selection="MAYBE"),
        "unknown decision": lambda d: d.update(decision="PASS"),
        "missing attempts": lambda d: d["experiments"][0].pop("attempts"),
        "bad config digest": lambda d: d.update(campaignConfigDigest="md5:1"),
        "bad harness digest": lambda d: d["experiments"][0].update(harnessDigest="sha256:1"),
        "bad snapshot digest": lambda d: d["sourceIdentity"].update(snapshotSha256="xyz"),
        "score as string": lambda d: d["mutationSummary"].update(score="0.5"),
        "score above one": lambda d: d["mutationSummary"].update(score=2),
        "cleanup before snapshot": lambda d: d.update(stages=list(reversed(d["stages"]))),
        "attempt without verdict": lambda d: d["experiments"][0]["attempts"][0].update(verdict=None),
        "unknown requirement": lambda d: d["acceptanceEvaluation"]["requirements"][0].update(requirement="requireMagic"),
        "excluded changed": lambda d: d["sourceIdentity"].update(excluded=[]),
        "missing roots": lambda d: d["sourceIdentity"].pop("roots"),
        "missing experiment root": lambda d: d["experiments"][0].pop("root"),
        "proof rate as string": lambda d: d["guardrailSummary"].update(proofRate="1"),
        "missing proof rate": lambda d: d["guardrailSummary"].pop("proofRate"),
        "parallelism 0": lambda d: d.update(parallelism=0),
        "parallelism 9": lambda d: d.update(parallelism=9),
        "tool with another kind": lambda d: d.update(tools=[dict(d["experiments"][0]["attempts"][0]["observations"][0], id="tool:x")]),
    }.items():
        bad = copy.deepcopy(doc)
        edit(bad)
        check(not valid(ev, bad), f"campaign evidence counterexample accepted: {label}")


def v5_checks(binary, tmp):
    """The v1alpha4 operator example and opted-in old inputs emit valid v1alpha5."""
    v5 = validator(load("evidence-v1alpha5.schema.json"))
    h4 = validator(load("harness-v1alpha4.schema.json"))
    ex = ROOT / "examples"
    project = tmp / "operators"
    shutil.copytree(ex / "operators", project)
    harness4 = json.loads((project / "invaris.json").read_text())
    check(valid(h4, harness4), "operator example harness violates harness-v1alpha4 schema")
    docs = {}

    def emit(label, cwd, args, want_exit, want_decision):
        code, out, err = run_cli(binary, cwd, *args)
        check(code == want_exit, f"v5 {label}: exit {code}, want {want_exit} ({err.strip()})")
        try:
            doc = json.loads(out)
        except ValueError:
            check(False, f"v5 {label}: stdout is not JSON")
            return
        errors = sorted(v5.iter_errors(doc), key=lambda e: list(e.path))
        check(not errors, f"v5 {label}: report violates schema: {errors[0].message if errors else ''}")
        check(doc.get("schemaVersion") == "invaris.evidence/v1alpha5" and doc.get("decision") == want_decision, f"v5 {label}: version or decision")
        docs[label] = doc

    for action in ("run", "check", "challenge"):
        emit(f"operators {action}", project, [action], 0, "ACCEPT")
    emit("operators campaign", project, ["campaign"], 0, "ACCEPT")
    emit("structured check opted in", ex / "structured", ["check", "--evidence-version", "v1alpha5"], 0, "ACCEPT")
    emit("legacy challenge opted in", ex, ["challenge", "--evidence-version", "v1alpha5", "invaris.json"], 0, "ACCEPT")
    emit("mutate opted in", ex / "mutation", ["mutate", "--evidence-version", "v1alpha5", "survived.json"], 1, "REJECT")
    emit("mutation campaign opted in", ex / "mutation", ["campaign", "--evidence-version", "v1alpha5", "campaign.json"], 1, "REJECT")
    # A preimage that does not match: REJECTED, INCONCLUSIVE, REFUSE.
    stale = tmp / "operators-stale"
    shutil.copytree(ex / "operators", stale)
    (stale / "notes.txt").write_text("edited after authoring\n")
    emit("operators stale preimage", stale, ["challenge"], 2, "REFUSE")
    rejected = [m for m in docs.get("operators stale preimage", {}).get("mutationMetadata", []) if m["application"] == "REJECTED"]
    check(len(rejected) == 1 and rejected[0]["beforeSha256"] is None, "stale preimage must give one REJECTED entry without hashes")

    def mutated(base, edit):
        doc = copy.deepcopy(base)
        edit(doc)
        return doc

    accepted = docs.get("operators challenge")
    if accepted:
        for key in ("engineVersion", "mutationMetadata", "commandDigests", "target"):
            check(not valid(v5, mutated(accepted, lambda d, k=key: d.pop(k))), f"v5 report missing {key} accepted")
        negatives = {
            "v1alpha2 schemaVersion": lambda d: d.update(schemaVersion="invaris.evidence/v1alpha2"),
            "root path": lambda d: d.update(target="/home/user/project"),
            "argv": lambda d: d["observations"][0].update(args=["scan.sh"]),
            "stdout": lambda d: d["observations"][0].update(stdout="{}"),
            "executable path": lambda d: d["observations"][0]["executable"].update(path="/bin/sh"),
            "proof detail": lambda d: d["proofs"][0].update(detail="free text"),
            "unknown operator": lambda d: d["mutationMetadata"][0].update(operator="replace"),
            "operator version 2": lambda d: d["mutationMetadata"][0].update(operatorVersion="2"),
            "fixture on whitespace": lambda d: d["mutationMetadata"][0].update(fixture="invaris-test-token-v1"),
            "secret without fixture": lambda d: d["mutationMetadata"][2].pop("fixture"),
            "applied without hashes": lambda d: d["mutationMetadata"][0].update(beforeSha256=None),
            "not applied with hashes": lambda d: d["mutationMetadata"][0].update(application="NOT_APPLIED"),
            "bad reproductionId": lambda d: d["mutationMetadata"][0].update(reproductionId="abc"),
            "bad command digest": lambda d: d["commandDigests"][0].update(sha256="md5:x"),
            "metadata unknown field": lambda d: d["mutationMetadata"][0].update(seed=1),
        }
        for label, edit in negatives.items():
            check(not valid(v5, mutated(accepted, edit)), f"v5 counterexample accepted: {label}")
    campaign = docs.get("operators campaign")
    if campaign:
        for label, edit in {
            "campaign without effectiveness": lambda d: d.pop("effectiveness"),
            "campaign attempt detail": lambda d: d["experiments"][0]["attempts"][0].update(detail="free text"),
            "campaign tool argv": lambda d: d["experiments"][0]["attempts"][0]["observations"][0].update(args=["x"]),
        }.items():
            check(not valid(v5, mutated(campaign, edit)), f"v5 counterexample accepted: {label}")
    for label, edit in {
        "builtin and literal mixed": lambda d: d["challenges"][0].update(before="a", after="b"),
        "builtin without preimage": lambda d: d["challenges"][0]["mutation"].pop("preimageSha256"),
        "builtin version 2": lambda d: d["challenges"][0]["mutation"].update(version="2"),
        "builtin unknown option": lambda d: d["challenges"][0]["mutation"].update(seed=1),
        "secret without fixture": lambda d: d["challenges"][2]["mutation"].pop("fixture"),
        "fixture on crlf": lambda d: d["challenges"][1]["mutation"].update(fixture="invaris-test-token-v1"),
        "v1alpha2 version": lambda d: d.update(version="invaris.dev/v1alpha2"),
    }.items():
        check(not valid(h4, mutated(harness4, edit)), f"harness-v1alpha4 counterexample accepted: {label}")
    # The old v1alpha2 harness schema still refuses the new mutation field.
    check(not valid(validator(load("harness-v1alpha2.schema.json")), mutated(harness4, lambda d: d.update(version="invaris.dev/v1alpha2"))), "harness-v1alpha2 accepted a built-in mutation")


def diagnostics_checks(binary, tmp):
    """`explain` reads a real report of every version and `doctor` inspects every example harness."""
    ev, dv = validator(load("explanation-v1alpha1.schema.json")), validator(load("doctor-v1alpha1.schema.json"))
    ex = ROOT / "examples"
    produced = {}

    def report(label, cwd, args, want_version):
        # Write the report with --report so explain reads exactly what a user would keep.
        path = tmp / f"explain-{len(produced)}.json"
        code, out, err = run_cli(binary, cwd, "--report", str(path), *args)
        check(code in (0, 1, 2) and path.exists(), f"explain input {label}: exit {code}, no report ({err.strip()})")
        if not path.exists():
            return
        check(json.loads(path.read_text()).get("schemaVersion") == want_version, f"explain input {label}: wrong report version")
        produced[label] = path

    report("v1alpha2 challenge", ex / "structured", ["challenge"], "invaris.evidence/v1alpha2")
    report("v1alpha3 mutate", ex / "mutation", ["mutate", "survived.json"], "invaris.evidence/v1alpha3")
    report("v1alpha4 campaign", ex / "mutation", ["campaign", "campaign.json"], "invaris.evidence/v1alpha4")
    report("v1alpha5 challenge", ex / "operators", ["challenge"], "invaris.evidence/v1alpha5")
    report("v1alpha5 campaign", ex / "operators", ["campaign"], "invaris.evidence/v1alpha5")
    explanations = {}
    for label, path in produced.items():
        code, out, err = run_cli(binary, ROOT, "explain", "--format", "json", str(path))
        check(code == 0, f"explain {label}: exit {code} ({err.strip()})")
        try:
            doc = json.loads(out)
        except ValueError:
            check(False, f"explain {label}: stdout is not JSON")
            continue
        errors = sorted(ev.iter_errors(doc), key=lambda e: list(e.path))
        check(not errors, f"explain {label}: violates schema: {errors[0].message if errors else ''}")
        check(doc.get("report", {}).get("schemaVersion") == json.loads(path.read_text())["schemaVersion"], f"explain {label}: report version not carried")
        explanations[label] = doc
        code, text, _ = run_cli(binary, ROOT, "explain", str(path))
        check(code == 0 and text.rstrip().endswith("Explained offline from the report; nothing was run."), f"explain {label}: text output")
    # A tampered decision must be refused, not interpreted.
    if "v1alpha2 challenge" in produced:
        doc = json.loads(produced["v1alpha2 challenge"].read_text())
        doc["decision"] = "REJECT" if doc["decision"] != "REJECT" else "ACCEPT"
        bad = tmp / "explain-tampered.json"
        bad.write_text(json.dumps(doc))
        code, out, _ = run_cli(binary, ROOT, "explain", "--format", "json", str(bad))
        check(code == 2 and out == "", "explain interpreted a report with a tampered decision")
    sample = explanations.get("v1alpha5 campaign")
    if sample:
        def mutated(edit):
            doc = copy.deepcopy(sample)
            edit(doc)
            return doc

        for label, edit in {
            "unknown class": lambda d: d["items"][0].update(**{"class": "great"}),
            "unknown limit": lambda d: d["limits"][0].update(code="trusted"),
            "no unauthenticated limit": lambda d: d.update(limits=[l for l in d["limits"] if l["code"] != "unauthenticated"]),
            "next without reason": lambda d: d["items"][0].update(reason=None, next="do it"),
            "multi-line meaning": lambda d: d["items"][0].update(meaning="a\nb"),
            "unknown field": lambda d: d.update(score=1),
        }.items():
            check(not valid(ev, mutated(edit)), f"explanation counterexample accepted: {label}")

    harnesses = [ex / "invaris.json", ex / "structured" / "invaris.json", ex / "v1alpha2" / "invaris.json",
                 ex / "provider" / "invaris.json", ex / "operators" / "invaris.json", ex / "go-project" / "guardrail.json",
                 ex / "go-project" / "mutation-killed.json", ex / "mutation" / "killed.json", ex / "forbidden-dependency" / "invaris.json"]
    sample_doctor = None
    for path in harnesses:
        if not path.exists():
            continue
        label = str(path.relative_to(ROOT))
        code, out, err = run_cli(binary, ROOT, "doctor", "--format", "json", str(path))
        # 0: nothing failed; 1: a setup check failed (for example a missing tool). Both are valid output.
        check(code in (0, 1), f"doctor {label}: exit {code} ({err.strip()})")
        try:
            doc = json.loads(out)
        except ValueError:
            check(False, f"doctor {label}: stdout is not JSON")
            continue
        errors = sorted(doc and dv.iter_errors(doc), key=lambda e: list(e.path))
        check(not errors, f"doctor {label}: violates schema: {errors[0].message if errors else ''}")
        check(all(c["executed"] is False for c in doc["checks"]), f"doctor {label}: a check claims it executed something")
        counts = {s: sum(1 for c in doc["checks"] if c["status"] == s) for s in ("pass", "fail", "warn", "skipped")}
        check(counts == doc["summary"], f"doctor {label}: summary does not match the checks")
        check((code == 1) == (counts["fail"] > 0), f"doctor {label}: exit code disagrees with the failures")
        sample_doctor = sample_doctor or doc
    # A failed load skips harness inspection but still reports selection and Git status.
    broken = tmp / "doctor-broken.json"
    broken.write_text("{")
    code, out, _ = run_cli(binary, ROOT, "doctor", "--format", "json", str(broken))
    doc = json.loads(out) if out else {}
    check(code == 1 and valid(dv, doc) and [c["id"] for c in doc.get("checks", [])] ==
          ["harness.load", "inspection", "harness.selection", "harness.git"], "doctor on an invalid harness")
    check(run_cli(binary, ROOT, "doctor", str(tmp / "missing.json"))[0] == 2, "doctor on a missing file must exit 2")
    if sample_doctor:
        def mutated(edit):
            doc = copy.deepcopy(sample_doctor)
            edit(doc)
            return doc

        for label, edit in {
            "executed true": lambda d: d["checks"][0].update(executed=True),
            "unknown status": lambda d: d["checks"][0].update(status="ok"),
            "missing summary": lambda d: d.pop("summary"),
            "unknown field": lambda d: d.update(score=1),
            "not loaded with extra checks": lambda d: d.update(harnessVersion=None),
        }.items():
            check(not valid(dv, mutated(edit)), f"doctor counterexample accepted: {label}")


def main():
    if shutil.which("go") is None:
        print("go toolchain not found", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="invaris-schema-") as tmp:
        tmp = Path(tmp)
        binary = tmp / "invaris"
        build = subprocess.run(["go", "build", "-o", str(binary), "./cmd/invaris"], cwd=ROOT, capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr, file=sys.stderr)
            return 2

        reports = {}

        def emit(label, cwd, action, config, want_exit, want_decision):
            code, out, err = run_cli(binary, cwd, action, config)
            check(code == want_exit, f"{label}: exit {code}, want {want_exit} ({err.strip()})")
            try:
                doc = json.loads(out)
            except ValueError:
                check(False, f"{label}: stdout is not JSON")
                return
            errors = sorted(evidence.iter_errors(doc), key=lambda e: list(e.path))
            check(not errors, f"{label}: report violates schema: {errors[0].message if errors else ''}")
            check(doc.get("decision") == want_decision, f"{label}: decision {doc.get('decision')}, want {want_decision}")
            check(doc.get("schemaVersion") == "invaris.evidence/v1alpha2", f"{label}: schemaVersion")
            reports[label] = doc

        ex = ROOT / "examples"
        for sub, name in (("", "v1alpha1 command"), ("structured", "v1alpha1 structured"), ("v1alpha2", "v1alpha2 structured")):
            d = ex / sub if sub else ex
            for action in ("check", "challenge"):
                emit(f"{name} {action}", d, action, "invaris.json", 0, "ACCEPT")

        # The provider example, with the freshly built provider injected by absolute path.
        provider_bin = tmp / "invaris-command-provider"
        build = subprocess.run(["go", "build", "-o", str(provider_bin), "./cmd/invaris-command-provider"], cwd=ROOT, capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr, file=sys.stderr)
            return 2
        project = tmp / "provider-project"
        shutil.copytree(ex / "provider", project)
        cfg = json.loads((project / "invaris.json").read_text())
        check(valid(harness, cfg), "example provider harness violates schema")
        cfg["adapters"][0]["program"] = str(provider_bin)
        (project / "invaris.json").write_text(json.dumps(cfg))
        emit("provider example check", project, "check", "invaris.json", 0, "ACCEPT")
        kinds = [o["kind"] for o in reports.get("provider example check", {}).get("observations", [])]
        check(kinds.count("discover") == 1, f"provider example: expected one discovery observation, saw {kinds}")
        (project / "source.txt").write_text("FORBIDDEN")
        emit("provider example violation", project, "check", "invaris.json", 1, "REJECT")
        cfg["adapters"][0]["program"] = str(tmp / "missing-provider")
        (project / "invaris.json").write_text(json.dumps(cfg))
        emit("provider example missing provider", project, "check", "invaris.json", 2, "REFUSE")

        v2 = {"version": "invaris.dev/v1alpha2", "name": "negative", "trustMode": "trusted-local", "networkPolicy": "unrestricted"}
        fails = {"id": "fails", "program": "sh", "args": ["-c", "exit 1"]}
        refuses = {"id": "refuses", "program": "invaris-missing-executable-4242"}
        for label, gate, code, decision in (
            ("failure-first", {"requiredGuards": ["fails", "refuses"], "precedence": "failure-first"}, 1, "REJECT"),
            ("refusal-first", {"requiredGuards": ["fails", "refuses"], "precedence": "refusal-first"}, 2, "REFUSE"),
        ):
            cfg = tmp / f"{label}.json"
            cfg.write_text(json.dumps({**v2, "guards": [fails, refuses], "gate": gate}))
            emit(f"precedence {label}", tmp, "check", str(cfg), code, decision)
        bad = tmp / "invalid.json"
        bad.write_text('{"version":"invaris.dev/v1alpha2"}')
        code, out, err = run_cli(binary, tmp, "check", str(bad))
        check(code == 2 and out == "" and err.strip() != "", "invalid harness must exit 2 with no stdout and a stderr diagnostic")

        # The v1alpha2 example harness must satisfy the harness schema.
        example = json.loads((ex / "v1alpha2" / "invaris.json").read_text())
        check(valid(harness, example), "example v1alpha2 harness violates schema")
        provider = {**v2, "adapters": [{"id": "a", "program": "p", "args": []}],
                    "guards": [{"id": "g", "adapterId": "a", "policyId": "p", "scope": ["src", "."], "options": {"k": [1]}}]}
        check(valid(harness, provider), "provider guard form should satisfy the harness schema")

        def mutated(base, edit):
            doc = copy.deepcopy(base)
            edit(doc)
            return doc

        harness_negatives = {
            "missing trustMode": lambda d: d.pop("trustMode"),
            "missing networkPolicy": lambda d: d.pop("networkPolicy"),
            "sandbox trust": lambda d: d.update(trustMode="sandboxed"),
            "restricted network": lambda d: d.update(networkPolicy="none"),
            "wrong version": lambda d: d.update(version="invaris.dev/v1alpha1"),
            "unknown field": lambda d: d.update(extra=1),
            "unsafe writable path": lambda d: d.update(writablePaths=["../x"]),
            "absolute writable path": lambda d: d.update(writablePaths=["/x"]),
            "bad precedence": lambda d: d["gate"].update(precedence="whatever"),
            "policy as string": lambda d: d.update(policies=["a"]),
            "timeout 301": lambda d: d["guards"][0].update(timeoutSeconds=301),
            "guard mixes forms": lambda d: d["guards"][0].update(adapterId="a"),
            "challenge without file": lambda d: d["challenges"][0].pop("file"),
        }
        for label, edit in harness_negatives.items():
            check(not valid(harness, mutated(example, edit)), f"harness counterexample accepted: {label}")
        check(not valid(harness, mutated(provider, lambda d: d["guards"][0].pop("scope"))), "harness counterexample accepted: provider guard without scope")
        check(not valid(harness, mutated(provider, lambda d: d["guards"][0].update(program="x"))), "harness counterexample accepted: provider guard with program")

        # Evidence counterexamples derived from a real accepted report.
        accepted = reports.get("v1alpha2 structured challenge")
        if accepted is None:
            check(False, "no accepted v1alpha2 report to derive counterexamples from")
        else:
            for key in evidence_schema["required"]:
                check(not valid(evidence, mutated(accepted, lambda d, k=key: d.pop(k))), f"evidence missing {key} accepted")
            negatives = {
                "unknown top-level field": lambda d: d.update(extra=1),
                "old schemaVersion": lambda d: d.update(schemaVersion="invaris.evidence/v1alpha1"),
                "invalid decision": lambda d: d.update(decision="PASS"),
                "invalid action": lambda d: d.update(action="verify"),
                "short runId": lambda d: d.update(runId="abc"),
                "malformed digest": lambda d: d.update(configDigest="md5:abc"),
                "ACCEPT without digest": lambda d: d.update(configDigest=None),
                "ACCEPT without target count": lambda d: d.update(targetCount=None),
                "ACCEPT with zero target count": lambda d: d.update(targetCount=0),
                "invalid proof status": lambda d: d["proofs"][0].update(status="PASS"),
                "invalid proof strength": lambda d: d["proofs"][0].update(evidenceStrength="medium"),
                "invalid check status": lambda d: d["proofs"][0]["baseline"].update(status="PROVEN"),
                "proof missing baseline key": lambda d: d["proofs"][0].pop("baseline"),
                "proof missing mutation key": lambda d: d["proofs"][0].pop("mutation"),
                "proof missing stages key": lambda d: d["proofs"][0].pop("stages"),
                "PROVEN without mutation": lambda d: d["proofs"][0].update(mutation=None),
                "mutation bad hash": lambda d: d["proofs"][0]["mutation"].update(afterSha256="xyz"),
                "mutation unknown field": lambda d: d["proofs"][0]["mutation"].update(extra=1),
                "PROVEN with failed cleanup": lambda d: d["proofs"][0]["stages"][-1].update(status="FAILED"),
                "PROVEN without cleanup stage": lambda d: d["proofs"][0].update(stages=[s for s in d["proofs"][0]["stages"] if s["name"] != "cleanup"]),
                "unknown stage name": lambda d: d["proofs"][0]["stages"][0].update(name="setup"),
                "negative stage duration": lambda d: d["proofs"][0]["stages"][0].update(durationMs=-1),
                "artifact bad hash": lambda d: d.update(artifacts=[{"path": "a", "sha256": "xyz", "bytes": 1}]),
                "ACCEPT artifact without bytes": lambda d: d.update(artifacts=[{"path": "a", "sha256": "0" * 64, "bytes": 0}]),
                "invalid precedence": lambda d: d["gate"].update(precedence=""),
                "invalid compatibility": lambda d: d["compatibility"].update(status="unknown"),
            }
            for label, edit in negatives.items():
                check(not valid(evidence, mutated(accepted, edit)), f"evidence counterexample accepted: {label}")
            # A non-ACCEPT report may carry explicit nulls.
            refused = reports.get("precedence refusal-first")
            if refused:
                check(valid(evidence, mutated(refused, lambda d: d.update(configDigest=None, targetCount=None))), "REFUSE report with null unknowns rejected")

        mutation_checks(binary)
        campaign_checks(binary, tmp)
        v5_checks(binary, tmp)
        diagnostics_checks(binary, tmp)

    adapter_checks()
    print(f"{checks} checks, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
