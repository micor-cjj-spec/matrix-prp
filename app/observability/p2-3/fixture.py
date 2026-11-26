"""Bounded synthetic workload, no PRP data or services."""
from pathlib import Path
import os
import time

# Keep an identifiable anonymous allocation resident.
memory = bytearray(24 * 1024 * 1024)
for offset in range(0, len(memory), 4096):
    memory[offset] = 1
Path("/tmp/ready").touch()
while True:
    if Path("/tmp/work").exists():
        # Rate-limited CPU work; actual allocation remains well below 96 MiB.
        until = time.monotonic() + 0.15
        n = 0
        while time.monotonic() < until:
            n = (n + 1) % 1000003
        if not Path("/tmp/wrote").exists():
            with open("/tmp/p2-io", "wb", buffering=0) as output:
                output.write(b"x" * (2 * 1024 * 1024))
                os.fsync(output.fileno())
            Path("/tmp/wrote").touch()
    time.sleep(0.15)
