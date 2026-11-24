#!/bin/bash

set -euo pipefail

dnf5 --setopt=fedora.countme=false --setopt=updates.countme=false install -y llama-cpp
cp -a /ctx/system_files/. /
