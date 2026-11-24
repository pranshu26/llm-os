# Local inference under CPU contention

Run this from a non-root login session on the LLM OS image with its systemd
user manager active. The host must expose the cgroup v2 CPU controller to the
user manager. The benchmark uses `python3`, `llm-run`, `llama-bench` and
`taskset`.

```sh
python3 benchmarks/cpu-inference.py /absolute/path/to/model.gguf
```

The script takes a local GGUF and makes no network requests. For a small
fixture, use the [GGML project’s TinyStories 15M Q4_0 model](https://huggingface.co/ggml-org/models/blob/499bc8821c6b12b4e53c5bffcb21ec206f212d81/tinyllamas/stories15M-q4_0.gguf)
with SHA-256 `66967fbece6dbe97886593fdbb73589584927e29119ec31f08090732d1861739`.

The benchmark pins two single-threaded `llama-bench` jobs to the same allowed
logical CPU. In the equal-weight control, both jobs run in `llm-interactive`.
In the weighted condition, the competing job moves to `llm-background`. The
measured job stays in `llm-interactive` for both conditions. Each sample starts
after competing decode has begun, and the script alternates the order of the
conditions across pairs. It reports JSON with actual CPU weights, individual
results, median generation latency and the median within-pair speedup.

The recorded CPU decode interval starts after model loading and warmup.
`llama-bench` measures synthetic decoding with no tokenization or sampling.
Desktop responsiveness, GPU performance and idle throughput require separate
tests.
