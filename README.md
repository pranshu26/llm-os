# LLM OS

An experimental Fedora 44 bootc image for running local inference alongside
background work on the same Linux machine. It packages llama.cpp and a
launcher that gives interactive processes more CPU time when LLM workloads
compete.

## Try it on a Linux test machine

Build the OCI image with Podman on a Linux machine. The build runs
`bootc container lint`.

```sh
podman build -f Containerfile -t localhost/llm-os:latest .
```

The inherited `just build-vm` recipe builds a QCOW2 disk from the local image
using [bootc-image-builder](https://github.com/osbuild/bootc-image-builder).
It requires Podman, Just, and a privileged image-builder run. Provision a
regular user through your VM install or cloud-init configuration and use
a disposable VM for first boot. CI builds and smoke-tests the OCI image.

From a regular login with a working systemd user session, run your own GGUF
model. No model weights are bundled. The server below listens on loopback.

```sh
llm-run interactive -- llama-server -m "$HOME/models/chat.gguf" --host 127.0.0.1 --port 8080
```

Start a background job from another terminal:

```sh
llm-run background -- ./index-documents
```

Use `systemd-cgls --user-unit llm.slice` to inspect the hierarchy and
`llm-run --help` to see the launcher options. The command and any subprocesses
normally inherit the same cgroup, along with your current working directory
and terminal.

## What Linux enforces

| User slice | CPU weight | Intended workloads |
| --- | ---: | --- |
| `llm-interactive.slice` | 100 | Chat, completions, and tasks the user is waiting for |
| `llm-background.slice` | 20 | Indexing, batch inference, and precomputation |

Both classes share the parent `llm.slice`. The kernel applies relative weights
when runnable tasks in those sibling cgroups compete for CPU. Either class
can use spare CPU. The policy depends on the cgroup v2 CPU controller being
available to the systemd user manager.

The priority applies to processes and their descendants. Requests handled by
one model server share that server's process priority. The launcher runs
commands with the current user's permissions. It sets CPU weights, and
memory, GPU scheduling, and access to user files are governed by the rest of
the system.

## Measure CPU contention

The [benchmark instructions](benchmarks/README.md) show how to compare this
policy against equal priority with two llama.cpp processes pinned to one CPU.

## Where this could go

1. Provide a per-user model broker so applications can share warm models
   and submit requests with a deadline, a priority, and a cancellation
   handle. The inference engine would still manage token batches and the KV
   cache. Measure time to first token and background completion together.
2. Defer new background work when Linux reports sustained CPU or memory
   stalls. Use cgroup limits for host RAM and engine or driver telemetry for
   accelerator memory. Measure desktop responsiveness, memory pressure,
   evictions, and power draw on real hardware.
3. Let users grant individual agent runs access to specific workspaces and
   tools. Use expiring access, structured tool calls, and a record of actions
   so users can review changes and revoke access. Keep cloud inference
   opt-in with explicit scope for the data sent.
4. Propose individual kernel changes once measurements show where existing
   interfaces fall short. Accelerator memory accounting and contention
   telemetry are candidates to investigate across drivers.

See [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html),
[Linux pressure stall information](https://docs.kernel.org/accounting/psi.html),
and [systemd resource control](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html).

This image derives from the [Universal Blue image template](https://github.com/ublue-os/image-template).
