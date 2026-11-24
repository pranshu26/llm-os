#!/bin/bash

set -euo pipefail

dnf5 install -y llama-cpp
cp -a /ctx/system_files/. /
