#!/usr/bin/env python3
"""Compare foreground CPU decode with equal and weighted Linux cgroups."""

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time


def start_background(command, log):
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=log,
        start_new_session=True,
    )


def wait_for_decode(process, log):
    deadline = time.monotonic() + 60
    while process.poll() is None and time.monotonic() < deadline:
        output = os.pread(log.fileno(), 65536, 0)
        if b"generation run 1/" in output:
            return
        time.sleep(0.02)
    output = os.pread(log.fileno(), 65536, 0).decode(errors="replace")
    raise RuntimeError(f"competing inference did not reach generation\n{output}")


def stop_background(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        process.wait()
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def cpu_weight(launcher, workload):
    result = subprocess.run(
        [launcher, workload, "--", "sh", "-c",
         'path=$(cut -d: -f3 /proc/self/cgroup) && '
         'cat "/sys/fs/cgroup${path%/*}/cpu.weight"'],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{workload} CPU weight unavailable\n{result.stderr}")
    return int(result.stdout)


def measure(launcher, bench, cpu, model, tokens, competing_class):
    workload = [
        "taskset", "--cpu-list", str(cpu), bench,
        "-m", str(model), "-ngl", "0", "-nkvo", "1", "-nopo", "1",
        "-t", "1", "-p", "0",
        "-n", str(tokens), "-o", "json",
    ]
    with tempfile.TemporaryFile() as log:
        background = start_background(
            [launcher, competing_class, "--", *workload, "-r", "32", "--progress"],
            log,
        )
        try:
            wait_for_decode(background, log)
            result = subprocess.run(
                [launcher, "interactive", "--", *workload, "-r", "1"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"foreground inference failed\n{result.stderr}")
            if background.poll() is not None:
                raise RuntimeError("competing inference stopped during the sample")
            (record,) = json.loads(result.stdout)
            return {
                "generation_ms": record["avg_ns"] / 1_000_000,
                "tokens_per_second": record["avg_ts"],
                "llama_cpp_commit": record.get("build_commit"),
            }
        finally:
            stop_background(background)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="local GGUF model file")
    parser.add_argument("--runs", type=int, default=5, help="number of paired runs")
    parser.add_argument("--tokens", type=int, default=128, help="tokens per sample")
    parser.add_argument("--cpu", type=int, help="CPU to pin both workloads to")
    parser.add_argument("--launcher", default="llm-run", help="path to llm-run")
    parser.add_argument("--bench", default="llama-bench", help="path to llama-bench")
    args = parser.parse_args()

    if not sys.platform.startswith("linux"):
        parser.error("Linux with a running systemd user manager is required")
    if args.runs < 2 or args.tokens < 1:
        parser.error("use at least two paired runs and a positive token count")
    if not args.model.is_file():
        parser.error(f"model file does not exist: {args.model}")
    launcher = shutil.which(args.launcher)
    bench = shutil.which(args.bench)
    if not launcher or not bench or not shutil.which("taskset"):
        parser.error("llm-run, llama-bench, and taskset must be executable")

    affinity = os.sched_getaffinity(0)
    cpu = min(affinity) if args.cpu is None else args.cpu
    if cpu not in affinity:
        parser.error(f"CPU {cpu} is outside this process's allowed CPU set")

    pairs = []
    try:
        weights = {
            mode: cpu_weight(launcher, mode)
            for mode in ("interactive", "background")
        }
        if weights["interactive"] <= weights["background"]:
            raise RuntimeError(f"interactive CPU weight must be higher: {weights}")
        for index in range(args.runs):
            modes = (("equal", "interactive"), ("weighted", "background"))
            if index % 2:
                modes = modes[::-1]
            pair = {}
            for mode, competing_class in modes:
                pair[mode] = measure(
                    launcher, bench, cpu, args.model.resolve(), args.tokens,
                    competing_class,
                )
            pairs.append(pair)
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")

    report = {
        "model": args.model.name,
        "cpu": cpu,
        "cpu_weights": weights,
        "kernel": os.uname().release,
        "tokens": args.tokens,
        "llama_cpp_commit": pairs[0]["equal"]["llama_cpp_commit"],
        "median_generation_ms": {
            mode: statistics.median(pair[mode]["generation_ms"] for pair in pairs)
            for mode in ("equal", "weighted")
        },
        "median_paired_speedup": statistics.median(
            pair["equal"]["generation_ms"] / pair["weighted"]["generation_ms"]
            for pair in pairs
        ),
        "pairs": pairs,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
