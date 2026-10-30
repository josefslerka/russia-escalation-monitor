#!/usr/bin/env python3
"""Validate, snapshot and publish a completed forecast to the configured repository."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess

from build_site import DATA, ROOT, PRAGUE, build, validate
from monitoring import FILES as MONITOR_FILES, LOG_FILES
import forecasting

EXPECTED_REMOTES = {
    "https://github.com/josefslerka/russia-escalation-monitor.git",
    "https://github.com/josefslerka/russia-escalation-monitor",
    "git@github.com:josefslerka/russia-escalation-monitor.git",
}
ALLOWED = re.compile(r"russia-escalation/(?:state\.json|evidence\.jsonl|watchlist\.json|geography\.json|" + '|'.join(re.escape(name) for name in MONITOR_FILES) + r"|reports/\d{4}-\d{2}-\d{2}-\d{4}(?:\.en)?\.md|snapshots/\d{4}-\d{2}-\d{2}-\d{4}\.json)")


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=check)


def preserve_history(ref="HEAD"):
    old_protocol = git('show', f'{ref}:russia-escalation/{forecasting.PROTOCOL}', check=False)
    if old_protocol.returncode == 0:
        forecasting.preserve_protocol(json.loads(old_protocol.stdout), json.loads((DATA / forecasting.PROTOCOL).read_text()), datetime.now(PRAGUE))
    for name in ('evidence.jsonl', *LOG_FILES):
        old = git("show", f"{ref}:russia-escalation/{name}", check=False)
        if old.returncode == 0:
            current = (DATA / name).read_text()
            if not current.startswith(old.stdout):
                raise ValueError(f"Evidence/audit history changed in {name}; append new records instead of rewriting old ones")
    historic_paths = git("ls-tree", "-r", "--name-only", ref, "russia-escalation/reports", "russia-escalation/snapshots", check=False)
    for name in historic_paths.stdout.splitlines():
        before = git("show", f"{ref}:{name}").stdout
        path = ROOT / name
        if not path.is_file() or path.read_text() != before:
            raise ValueError(f"An archived report/snapshot changed or disappeared: {name}")


def snapshot(state):
    path = DATA / "snapshots" / (Path(state["last_report"]).stem + ".json")
    content = (DATA / "state.json").read_text()
    if path.exists():
        if json.loads(path.read_text()) != state:
            raise ValueError("A different snapshot already exists for this assessment timestamp")
    else:
        path.parent.mkdir(exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)


def metadata_guard(ref="HEAD"):
    """A metadata publication cannot silently masquerade as a new assessment."""
    previous = git('show', f'{ref}:russia-escalation/state.json').stdout
    if (DATA / 'state.json').read_text() != previous:
        raise ValueError('Metadata publication must preserve state.json byte-for-byte')
    for folder in ('reports', 'snapshots'):
        previous_paths = set(git('ls-tree', '-r', '--name-only', ref, f'russia-escalation/{folder}').stdout.splitlines())
        current_paths = {f'russia-escalation/{folder}/{path.name}' for path in (DATA / folder).iterdir() if path.is_file()}
        if previous_paths != current_paths:
            raise ValueError('Metadata publication cannot add/remove reports or snapshots')
    old = git('show', f'{ref}:russia-escalation/evidence.jsonl').stdout
    current = (DATA / 'evidence.jsonl').read_text()
    if not current.startswith(old):
        raise ValueError('Metadata publication cannot rewrite evidence')
    for line in current[len(old):].splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get('intake_type') != 'retrospective_backfill' or item.get('forecast_integration') != 'pending_review':
                raise ValueError('Metadata evidence intake must be an explicitly pending retrospective backfill')


def prepare(metadata_only=False):
    state, _, _ = validate()
    preserve_history()
    if metadata_only:
        metadata_guard()
    else:
        from monitor import register_forecasts
        register_forecasts()
        snapshot(state)
    build()
    from check_site import check
    check()
    return state


def publish(metadata_only=False):
    if git("remote", "get-url", "origin").stdout.strip() not in EXPECTED_REMOTES:
        raise ValueError("Unexpected origin: publication is restricted to the approved repository")
    if git("diff", "--cached", "--name-only").stdout.strip():
        raise ValueError("The staging area must be empty before automatic publication")
    branch = git("branch", "--show-current").stdout.strip()
    if branch not in {"main", "master"}:
        raise ValueError("Automatic publication must run on main or master")
    state, _, _ = validate()
    cutoff = datetime.fromisoformat(state["assessment_time"])
    now = datetime.now(PRAGUE)
    if not metadata_only and (cutoff.astimezone(PRAGUE).date() != now.date() or cutoff > now):
        raise ValueError("Only a completed assessment from today can be published automatically")
    git("fetch", "origin", branch)
    remote = f"origin/{branch}"
    if git("merge-base", "--is-ancestor", remote, "HEAD", check=False).returncode:
        raise ValueError("The remote has changes not present locally; reconcile them before publishing")
    # Do not push unrelated local commits either, even when the working tree is clean.
    outgoing = git("log", "--format=", "--name-only", f"{remote}..HEAD").stdout.splitlines()
    if any(name and not ALLOWED.fullmatch(name) for name in outgoing):
        raise ValueError("Unpublished code or unrelated commits require a deliberate manual push")
    preserve_history(remote)
    if metadata_only:
        metadata_guard(remote)
    prepare(metadata_only)
    changed = []
    for entry in git("status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "russia-escalation").stdout.split("\0"):
        if not entry:
            continue
        status, name = entry[:2], entry[3:]
        if not ALLOWED.fullmatch(name) or "D" in status or "R" in status:
            raise ValueError(f"Unexpected change in forecast data: {name}")
        changed.append(name)
    if changed:
        git("add", "--", *changed)
        git("commit", "-m", f"{'monitoring metadata' if metadata_only else 'forecast'}: {state['assessment_time']}")
    ahead = git("rev-list", "--count", f"{remote}..HEAD").stdout.strip()
    if ahead != "0":
        git("push", "origin", f"HEAD:{branch}")
        print(f"Published {'metadata for unchanged assessment' if metadata_only else 'assessment'} {state['assessment_time']}; GitHub Actions will deploy Pages")
    else:
        print("The validated assessment is already on GitHub; no duplicate commit needed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--push", action="store_true", help="Commit only forecast data and push to the approved origin")
    parser.add_argument("--metadata-only", action="store_true", help="Publish coverage/geography/backfill without advancing state or creating a snapshot; may use an older assessment")
    options = parser.parse_args()
    try:
        if options.push:
            publish(options.metadata_only)
        else:
            prepare(options.metadata_only)
            print("Prepared locally; no commit or network write")
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        details = exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise SystemExit(f"Publication stopped: {details}") from exc
