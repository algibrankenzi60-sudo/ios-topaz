# J2 Prime XNU early-boot audit

## Result

The earlier 0x44000000 RAM candidate and its description were wrong. The captured FDT and the matching G532G MT6737T kernel DTS encode one bank as `reg = <0 0x40000000 0 0x80000000>`, which is the half-open 2 GiB interval `[0x40000000,0xc0000000)`, not a 128 MiB bank. All five retained live DTBs agree. The implementation now selects only `[0x80000000,0x84000000)`, a 64 MiB subset of the separately recorded `/proc/iomem` System RAM interval `[0x80000000,0x9f5c0000)`.

The captured FDT's dynamic `consys-reserve-memory` is 1 MiB, 2 MiB aligned, and has `alloc-ranges = [0x40000000,0x80000000)`, with no fixed `reg`. The new candidate starts at the exclusive end of that allocator range, so it intersects neither that dynamic allocation domain nor any static reserved-memory entry. The board DTS confirms the memory-bank encoding; `of_reserved_mem.c` allocates dynamic reservations from the FDT constraints; the MediaTek callback records the chosen base and uses the area for connectivity EMI sharing. [G532G board DTS](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/arch/arm/boot/dts/mt6737t_grandpplte_cis_ser_04.dts), [MT6735 reserved-memory DTS](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/arch/arm/boot/dts/mt6735.dtsi), [reserved-memory allocator](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/drivers/of/of_reserved_mem.c), [MediaTek consys callback](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/drivers/misc/mediatek/connectivity/common/conn_soc/mt6735/mtk_wcn_consys_hw.c).

The raw `/proc/iomem` text was not retained as a file; its contiguous high-RAM interval survives in `J2-XNU-PORT.md`. Therefore the candidate is source- and FDT-consistent, but the exact runtime map and any secure/firmware carve-outs have not been independently re-read. A boot payload that fits in the recovery partition is not, by that fact, safe to execute.

## Loader and handoff

The physical MT6737 shim contract is established: the stock loader places its 16 KiB image at `0x40004000`, the shim invokes MediaTek SMC `0x82000200`, and TrustZone enters AArch64 at `0x40008000`. The four-colour framebuffer probe on this handset verifies that the shim reached an AArch64 payload and that the payload could write the display. This proves mode switch and second-stage entry, not the XNU handoff itself. The shim source and build artifact are under `/mnt/d/J2-iOS-audit-20261027/mt6735-bootshim` and `bootshim-build/`.

The J2 second stage is linked at the observed entry. It validates the package and segment table, converts high XNU VAs to physical addresses using a checked offset (`physBase + (VA - virtBase)`), copies each segment, clears BSS, flushes/invalidate data cache for the written ranges, builds a version-2 ARM64 `boot_args` block, maps its ADT pointer back to the XNU VA window, and branches to the Mach-O entry with `x0 = boot_args physical address`. Compile-time layout assertions match XNU 8796's `pexpert/pexpert/arm64/boot.h`. The loader stack is at `0x80f00000`, in the selected RAM window below the kernel's first destination segment; the shim/payload source remains below `0x41000000`.

The kernel package is an uncompressed 4 KiB ARM64 Mach-O with 10 segments and no chained fixups. Kernel, ADT, and boot_args fit the chosen 64 MiB window. The package is separate from Topaz's SWEET format. The 16 MiB recovery-size check remains a packaging limit only.

Latest offline build (`j2prime-earlyboot-audit-20261028`): kernel 16,351,688 bytes (SHA-256 `2d716f57c351f126317970da6512dfe2f9f8eb2354c9b9e672237d5c03818eea`); payload 15,748,992 bytes; combined diagnostic kernel 15,769,472 bytes (SHA-256 `cd05e2188a4653aaa5bc2471335e5c749063b3369ea2f152448784275b839746`). The segments occupy `[0x81004000,0x81fe81c8)`, the page-aligned kernel end is `0x81fe9000`, ADT is at `0x81fe9000`, boot_args at `0x81fea000`, and about 32 MiB of the 64 MiB candidate remains beyond boot_args. The diagnostic artifact stays outside the repository and is labelled not for flashing.

## Offline checks and limits

`j2boot/build-offline.sh OUTPUT_DIR` cross-compiles and links the loader with the installed Android NDK for Windows, audits the FDT, packages the kernel, and composes the diagnostic image from the known 16 KiB shim + loader + package. Audit all five saved live DTBs using:

```sh
for f in /mnt/d/J2-iOS-audit-20261027/live-boot-*.dtb; do
  python3 tools/mkadt_j2.py /tmp/j2prime.adt --dtb "$f"
done
```

The script rejects candidate windows outside captured RAM, overlapping static reservations, or intersecting any declared dynamic allocation range. It does not claim to know the allocator's selected consys base. No QEMU ARM64 executable is installed in this environment, and the loader has not been run under emulation or on the handset. The phone is not currently visible to ADB/fastboot.

### Assessment

**Not yet cleared for an early-boot device test.** The static memory-map contradiction and VA-to-PA arithmetic defect are fixed; source-level constraints place the selected window outside the captured consys allocation range; loader layout and package bounds are checked offline. The remaining minimum check is one read-only snapshot while LineageOS is running:

```sh
adb shell su -c 'cat /proc/iomem; dmesg | grep -i consys-reserve-memory'
```

This reads the live RAM map and the resolved 1 MiB consys base so it can be compared with `[0x80000000,0x84000000)`. It does not write storage. ADB currently lists no device, so this snapshot could not be collected in this run. After it passes, the next experiment should be a temporary boot-path test; no partition flash is authorized or performed.

No GICv2 interrupt delivery, timer tick, XNU entry execution, console after the jump, or boot beyond earliest XNU startup has been verified. This is an early-boot kernel diagnostic, not iOS userspace.
