#!/usr/bin/env python3
"""Guard J2 Prime's real IODT platform-expert registration and build selection."""
from pathlib import Path

patch = Path("xnu/patches/0965-j2prime-register-platform-expert.patch").read_text()
checks = (
    "#if defined(ARM64_BOARD_CONFIG_J2PRIME)",
    "'IOClass'         = J2PrimePlatformExpert;",
    "'IONameMatch'     = 'samsung,j2prime';",
    "'IONameMatch'     = 'samsung,sm-g532g';",
    "options j2prime_platform",
    "J2PrimePlatformExpert.cpp                  optional iokitcpp j2prime_platform",
    "class J2PrimePlatformExpert : public IODTPlatformExpert",
    "J2PrimePlatformExpert::processTopLevel",
    'sweet_early_mark(16, "J2 expert start entered")',
    'sweet_early_mark(17, "J2 base expert start returned")',
    'sweet_early_mark(18, "J2 expert registered")',
    'sweet_early_mark(19, "J2 processTopLevel entered")',
    'sweet_early_mark(20, "J2 processTopLevel done")',
    "IODTPlatformExpert::start(provider)",
    "registerService();",
    "createNubs(this, IODTFindMatchingEntries(cpus, kIODTExclusive, NULL));",
)
for item in checks:
    if item not in patch:
        raise SystemExit(f"J2 platform-expert patch is missing: {item}")

added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
if "SweetPlatformExpert" in added or "Topaz" in added or "sweet_platform" in added:
    raise SystemExit("J2 platform patch must not pull in SWEET/Topaz platform drivers")

print("J2 Prime IODT platform-expert patch checks passed")
