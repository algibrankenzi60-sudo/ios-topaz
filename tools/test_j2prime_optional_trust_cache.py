#!/usr/bin/env python3
"""Ensure J2 handles absent Image4/AMFI using XNU's existing optional path."""
from pathlib import Path

patch = Path("xnu/patches/0964-j2prime-optional-trust-cache.patch").read_text()
required = (
    "#if defined(SWEET) || defined(J2PRIME)",
    "if (img4if == NULL || amfi == NULL)",
    "trust_cache_rt = NULL;",
    "trust_cache_mut_rt = NULL;",
    "J2PRIME: trust caches unavailable (Image4/AMFI not installed)",
    "return KERN_NOT_SUPPORTED;",
    "return KERN_NOT_FOUND;",
)
missing = [item for item in required if item not in patch]
if missing:
    raise SystemExit("J2 optional trust-cache patch is incomplete: " + ", ".join(missing))
if patch.count("#if defined(SWEET) || defined(J2PRIME)") != 6:
    raise SystemExit("expected all six existing SWEET null-runtime guards for J2")
if "return KERN_SUCCESS;" in patch:
    raise SystemExit("unexpected fake success return in trust-cache patch")
print("J2 optional trust-cache patch checks passed")
