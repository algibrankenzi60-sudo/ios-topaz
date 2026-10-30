#!/usr/bin/env python3
"""Verify J2 platform-expert start avoids recursively publishing itself."""
from pathlib import Path
import subprocess
import tempfile

patch_dir = Path("xnu/patches")
source_patch = (patch_dir / "0965-j2prime-register-platform-expert.patch").read_text()
added = "\n".join(line[1:] for line in source_patch.splitlines()
                if line.startswith("+") and not line.startswith("+++"))
start = added.split("J2PrimePlatformExpert::start(IOService *provider)", 1)[1]
start = start.split("\n+}", 1)[0]
assert "registerService();" in start  # this is the behavior the follow-up removes

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    target = root / "iokit/Kernel/arm/J2PrimePlatformExpert.cpp"
    target.parent.mkdir(parents=True)
    lines = source_patch.splitlines()
    begin = lines.index("--- a/iokit/Kernel/arm/J2PrimePlatformExpert.cpp")
    added_lines = []
    for line in lines[begin + 2:]:
        if line.startswith("+#endif /* J2PRIME */"):
            break
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
    target.write_text("\n".join(added_lines) + "\n")
    subprocess.run(["git", "apply", str((patch_dir / "0970-j2prime-expert-exit-checkpoint.patch").resolve())],
                   cwd=root, check=True)
    subprocess.run(["git", "apply", str((patch_dir / "0971-j2prime-avoid-reentrant-expert-publication.patch").resolve())],
                   cwd=root, check=True)
    result = target.read_text()
    body = result.split("J2PrimePlatformExpert::start(IOService *provider)", 1)[1]
    body = body.split("\n}", 1)[0]
    assert "registerService();" not in body
    assert "IOLog(\"J2PRIME: platform expert registered" not in body
    assert "J2 expert start exit path reached" not in body
    assert 'sweet_early_mark(18, "J2 expert start returning to caller")' in body
    assert body.index("IODTPlatformExpert::start(provider)") < body.index("return true;")
    assert body.index('sweet_early_mark(18, "J2 expert start returning to caller")') < body.index("return true;")

print("J2 expert start returns without recursively republishing itself")
