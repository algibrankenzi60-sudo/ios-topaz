# J2 Prime XNU kexec experiment

This branch builds a one-segment, RAM-only ARM kexec package for Galaxy Grand Prime+ SM-G532G / MT6737T. It does not write boot, recovery, userdata, or any other partition. The experiment is not a supported iOS port and has not been run on the handset.

## Current package

Built from XNU artifact `kernel.development.j2prime` (SHA-256 `2d716f57c351f126317970da6512dfe2f9f8eb2354c9b9e672237d5c03818eea`) with the J2 DT-derived ADT and 4 KiB page layout. The final image and its manifest are outside the git repository:

- `/mnt/d/J2-iOS-audit-20261027/j2prime-xnu-experiment-20261028/J2PRIME-KEXEC-DO-NOT-FLASH.bin`
- `/mnt/d/J2-iOS-audit-20261027/j2prime-xnu-experiment-20261028/manifest.json`
- Image length: 15,773,696 bytes
- Image SHA-256: `2a73c2f07ad5a00a5387f69ce859ae8ccb8f4d3dc6aab2c20f388b92afa9d48a`

The image layout is:

| Physical address | Contents |
|---|---|
| `0x84000000` | ARM32 kexec entry and 16 KiB trampoline |
| `0x84004000` | AArch64 loader (reserved 8 KiB) |
| `0x84006000` | `J2PRIME` package: ten Mach-O segments plus ADT |
| `0x85000000` | Exclusive end of the audited source window |

The trampoline follows the matching Samsung Linux ARM kexec relocation ABI: ARM state, initial registers ignored, stack reset to physical RAM, then `r0=0x82000200` and `r1=0x84004000` for the MT6737 SiP AArch32-to-AArch64 service. The matching kernel reference is [relocate_kernel.S at d88dd823](https://github.com/RodrigoAyuso/android_kernel_samsung_grandppltedx/blob/d88dd8238d239328549fe74694e43d915703b5ae/arch/arm/kernel/relocate_kernel.S). That repository is a source match, not proof of the exact running binary.

The AArch64 startup accepts EL1 or EL2. It cleans and invalidates data caches by set/way, disables current-stage MMU/caches, and, from EL2, enters EL1h with interrupts masked, stage-2 disabled, and EL1 timer access enabled. It sets a known physical stack before calling C. The loader copies Mach-O segments to `[0x81004000,0x81fe9000)`, places the 2,492-byte ADT at `0x81fe9000`, boot_args at `0x81fea000`, and four translation-table pages at `[0x81feb000,0x81fef000)`. `boot_args.topOfKernelData` covers these tables.

Before entering XNU, it builds 4 KiB tables matching XNU 8796's 4 KiB/39-bit VA/40-bit PA bootstrap: TTBR0 identity maps `0x80000000..0x85000000` in 2 MiB blocks; TTBR1 maps the 64 MiB kernel VA window beginning `0xfffffff006000000` to `0x80000000`. It programs TCR `0x22a519a519`, MAIR `0xff`, and XNU's A53-compatible SCTLR default `0x3454593d`, invalidates TLB/I-cache, then branches to the Mach-O entry VA `0xfffffff00740c488`, with physical boot_args in `x0`. XNU's matching startup source is [osfmk/arm64/start.s in the local XNU 8796 reference tree](/mnt/d/J2-iOS-audit-20261027/xnu-8796-reference/osfmk/arm64/start.s).

## Offline build and checks

```sh
./j2boot/build-kexec-offline.sh /mnt/d/J2-iOS-audit-20261027/j2prime-xnu-experiment-20261028
```

The builder checks the live `/proc/iomem` and memblock snapshot for the source window, cross-compiles the ARM32 and AArch64 stages with the installed Android NDK, builds the J2 ADT/package, creates the Android ARM32 kexec controller, runs MMU and ramoops host tests, and verifies the whole image and component hashes. `tools/verify_j2_experiment.py` checks the final byte layout and metadata.

## Later RAM-only launch and recovery

The launcher deliberately separates loading from execution. It Base64-encodes streams before sending them through ADB, avoiding Windows text-mode `0x1a`/Ctrl+Z truncation observed with raw stdin. `load` decodes the image and controller into `/dev` tmpfs, checks device-side SHA-256, and calls `kexec_load`; it does not reboot or execute the image. No persistent filesystem or partition is used. `execute` requires an explicit confirmation token and must only be used after separate user approval.

```sh
tools/j2-kexec-launch.sh IMAGE CONTROL MANIFEST load
tools/j2-kexec-launch.sh IMAGE CONTROL MANIFEST status
tools/j2-kexec-launch.sh IMAGE CONTROL MANIFEST unload
```

If Android still responds, `tools/j2-kexec-recover.sh` unloads a pending image; `--reboot-android` additionally requests a normal Android reboot. If the payload has already stopped Linux/ADB, the script cannot control the phone: force-restart it with the hardware buttons. The normal Samsung boot path and recovery partitions remain untouched.

## Limits

The four-colour recovery test previously proved only that the MT6737 service can enter a simple AArch64 payload in the recovery boot context. The last kexec runtime evidence proves Linux reached `machine_kexec()`'s `Bye!` log point; it does not prove the relocation stub or any new payload instruction ran. The current image's EL/cache normalization, mappings, loader, ADT, and XNU entry have only offline validation. The ramoops markers can later identify trampoline/loader stages, but `XNU_CALL` is written immediately before the branch and is not proof that XNU executed.

This package is ready for a first controlled **RAM-only evaluation**, not a known-working boot. XNU GIC/timer initialization, framebuffer handoff, UFS/root access, and all iOS userspace remain unverified. No execution was performed while building this artifact.
