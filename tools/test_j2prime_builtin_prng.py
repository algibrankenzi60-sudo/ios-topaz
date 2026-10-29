#!/usr/bin/env python3
"""Guard J2PRIME's built-in XNU PRNG registration and entropy digest."""
from pathlib import Path

patch = Path("xnu/patches/0963-j2prime-register-builtin-prng.patch").read_text()
required = (
    "#if defined(SWEET) || defined(J2PRIME)",
    "STARTUP(EARLY_BOOT, STARTUP_RANK_FIRST, sweet_prng_startup);",
    "register_and_init_prng(&sweet_prng_ctx, &funcs);",
    "J2PRIME PRNG: HMAC-SHA256 registered",
    "ccdigest_init(&ccsha256_ltc_di, entropy_data.sha256_ctx);",
    "ccdigest_update(&ccsha256_ltc_di, entropy_data.sha256_ctx, nbytes, data);",
    "ccdigest_final(&ccsha256_ltc_di, entropy_data.sha256_ctx, out);",
)
missing = [item for item in required if item not in patch]
if missing:
    raise SystemExit("J2 built-in PRNG patch is incomplete: " + ", ".join(missing))

# The PRNG path must reuse XNU's existing HMAC-DRBG, not a fake callback.
if "prng_funcs.refresh =" in patch or "return 0;" in patch:
    raise SystemExit("unexpected dummy PRNG callback in patch")
if patch.count("#if defined(SWEET) || defined(J2PRIME)") != 7:
    raise SystemExit("expected two PRNG and five entropy digest J2 guards")
print("J2 built-in PRNG patch checks passed")
