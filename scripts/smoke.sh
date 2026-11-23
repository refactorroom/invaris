#!/bin/sh
set -eu

case "${1-}" in
    "") real_provider=false ;;
    --with-dependency-cruiser) real_provider=true ;;
    *) echo "usage: sh scripts/smoke.sh [--with-dependency-cruiser]" >&2; exit 2 ;;
esac
test "$#" -le 1

cd "$(dirname "$0")/.."
root=$(pwd -P)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/invaris-smoke.XXXXXXXX")
trap 'rm -r -- "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local
go build -o "$tmp/invaris" ./cmd/invaris
go build -o "$tmp/invaris-command-provider" ./cmd/invaris-command-provider
export PATH="$tmp:$PATH"

examples_before=$(git -C "$root" status --porcelain --untracked-files=all -- examples 2>/dev/null || true)

count=0
accept() {
    "$tmp/invaris" --report "$tmp/report.json" "$1" "$2" >"$tmp/stdout.json"
    cmp "$tmp/report.json" "$tmp/stdout.json"
    grep -q '"schemaVersion": "invaris.evidence/v1alpha2"' "$tmp/stdout.json"
    grep -q '"decision": "ACCEPT"' "$tmp/stdout.json"
    rm "$tmp/report.json"
    count=$((count + 1))
    printf 'PASS %s %s\n' "$1" "$2"
}

for config in "$root/examples/invaris.json" "$root/examples/structured/invaris.json" "$root/examples/v1alpha2/invaris.json"; do
    for action in run check challenge; do
        accept "$action" "$config"
    done
done
for action in run check; do
    accept "$action" "$root/examples/provider/invaris.json"
done

for action in check challenge; do
    accept "$action" "$root/examples/forbidden-dependency/invaris.json"
done

# Built-in operators (v1alpha4 harness, v1alpha5 evidence), offline.
v5() {
    status=0
    (cd "$root/examples/operators" && "$tmp/invaris" --report "$tmp/report.json" "$@") >"$tmp/stdout.json" || status=$?
    test "$status" -eq 0
    cmp "$tmp/report.json" "$tmp/stdout.json"
    grep -q '"schemaVersion": "invaris.evidence/v1alpha5"' "$tmp/stdout.json"
    grep -q '"decision": "ACCEPT"' "$tmp/stdout.json"
    rm "$tmp/report.json"
    count=$((count + 1))
    printf 'PASS v1alpha5 %s examples/operators\n' "$*"
}
for action in check challenge campaign; do
    v5 "$action"
done
(cd "$root/examples/operators" && "$tmp/invaris" challenge --format compact) | grep -q '^ACCEPT proofs=3$'
count=$((count + 1))
printf 'PASS challenge --format compact examples/operators\n'

# explain reads a saved report offline and refuses a tampered one; doctor
# inspects a harness's setup without running harness commands.
(cd "$root/examples/operators" && "$tmp/invaris" --report "$tmp/explain-report.json" challenge) >/dev/null
"$tmp/invaris" explain "$tmp/explain-report.json" >"$tmp/explained.txt"
grep -q -- '-> detected' "$tmp/explained.txt"
grep -qx 'Explained offline from the report; nothing was run.' "$tmp/explained.txt"
"$tmp/invaris" explain --format json "$tmp/explain-report.json" | grep -q '"version": "invaris.explanation/v1alpha1"'
sed 's/"decision": "ACCEPT"/"decision": "REJECT"/' "$tmp/explain-report.json" >"$tmp/tampered.json"
status=0
"$tmp/invaris" explain "$tmp/tampered.json" >/dev/null 2>&1 || status=$?
test "$status" -eq 2
rm "$tmp/explain-report.json" "$tmp/tampered.json" "$tmp/explained.txt"
count=$((count + 1))
printf 'PASS explain examples/operators (detected; tampered report refused)\n'
"$tmp/invaris" doctor "$root/examples/structured/invaris.json" >"$tmp/doctor.txt"
test "$(tail -n 1 "$tmp/doctor.txt")" = 'doctor executed no harness commands; results describe setup only.'
grep -q '^Summary: .* 0 failed' "$tmp/doctor.txt"
rm "$tmp/doctor.txt"
count=$((count + 1))
printf 'PASS doctor examples/structured/invaris.json\n'

mutation() {
    cfg="$root/examples/mutation/$1.json"
    status=0
    "$tmp/invaris" --report "$tmp/report.json" mutate "$cfg" >"$tmp/stdout.json" || status=$?
    test "$status" -eq "$2"
    cmp "$tmp/report.json" "$tmp/stdout.json"
    grep -q '"schemaVersion": "invaris.evidence/v1alpha3"' "$tmp/stdout.json"
    grep -q "\"verdict\": \"$3\"" "$tmp/stdout.json"
    rm "$tmp/report.json"
    count=$((count + 1))
    printf 'PASS mutate %s (%s)\n' "$cfg" "$3"
}

mutation killed 0 KILLED
mutation survived 1 SURVIVED
mutation invalid 2 INVALID

# campaign DIR FILE EXIT DECISION [--only ID]
campaign() {
    dir=$1 file=$2 want=$3 decision=$4
    shift 4
    status=0
    (cd "$dir" && "$tmp/invaris" --report "$tmp/report.json" campaign "$@" "$file") >"$tmp/stdout.json" || status=$?
    test "$status" -eq "$want"
    cmp "$tmp/report.json" "$tmp/stdout.json"
    grep -q '"schemaVersion": "invaris.evidence/v1alpha4"' "$tmp/stdout.json"
    grep -q "\"decision\": \"$decision\"" "$tmp/stdout.json"
    rm "$tmp/report.json"
    count=$((count + 1))
    printf 'PASS campaign %s/%s %s(%s)\n' "${dir#"$root"/}" "$file" "${1:+$* }" "$decision"
}

campaign "$root/examples/mutation" campaign.json 1 REJECT
campaign "$root/examples/forbidden-dependency" campaign.json 0 ACCEPT

# The Go example runs the real Go toolchain and needs a warm or writable cache.
gp="$root/examples/go-project"
(cd "$gp" && go test -count=1 ./... >/dev/null)
printf 'PASS go test %s\n' "$gp"
count=$((count + 1))
for action in check challenge; do
    accept "$action" "$gp/guardrail.json"
done
go_mutation() {
    cfg="$gp/mutation-$1.json"
    status=0
    "$tmp/invaris" mutate "$cfg" >"$tmp/stdout.json" || status=$?
    test "$status" -eq "$2"
    grep -q "\"verdict\": \"$3\"" "$tmp/stdout.json"
    count=$((count + 1))
    printf 'PASS mutate %s (%s)\n' "$cfg" "$3"
}
go_mutation killed 0 KILLED
go_mutation survived 1 SURVIVED
go_mutation invalid 2 INVALID

campaign "$gp" campaign.json 2 REFUSE
campaign "$gp" campaign-accept.json 0 ACCEPT
campaign "$gp" campaign.json 1 REJECT --only mutation-survived
mkdir "$tmp/sequence"
export INVARIS_FIXTURE_STATE="$tmp/sequence"
campaign "$gp" campaign-mixed.json 2 REFUSE
grep -q '"stability": "MIXED"' "$tmp/stdout.json"

# No run may write back into the examples.
examples_after=$(git -C "$root" status --porcelain --untracked-files=all -- examples 2>/dev/null || true)
test "$examples_before" = "$examples_after"

if "$real_provider"; then
    export PATH="$root/adapters/dependency-cruiser:$PATH"
    for action in run check challenge; do
        accept "$action" "$root/examples/dependency-cruiser/invaris.json"
    done
else
    echo 'SKIP Dependency-Cruiser (offline tier)'
fi
printf '%s smoke checks passed\n' "$count"
