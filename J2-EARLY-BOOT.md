# J2 Prime XNU early-boot audit

## Result

The earlier 0x44000000 RAM candidate and its description were wrong. The captured FDT and the matching G532G MT6737T kernel DTS encode one bank as `reg = <0 0x40000000 0 0x80000000>`, which is the half-open 2 GiB interval `[0x40000000,0xc0000000)`, not a 128 MiB bank. All five retained live DTBs agree. The implementation now selects only `[0x80000000,0x84000000)`, a 64 MiB subset of the separately recorded `/proc/iomem` System RAM interval `[0x80000000,0x9f5c0000)`.

The captured FDT's dynamic `consys-reserve-memory` is 1 MiB, 2 MiB aligned, and has `alloc-ranges = [0x40000000,0x80000000)`, with no fixed `reg`. The new candidate starts at the exclusive end of that allocator range, so it intersects neither that dynamic allocation domain nor any static reserved-memory entry. The board DTS confirms the memory-bank encoding; `of_reserved_mem.c` allocates dynamic reservations from the FDT constraints; the MediaTek callback records the chosen base and uses the area for connectivity EMI sharing. [G532G board DTS](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/arch/arm/boot/dts/mt6737t_grandpplte_cis_ser_04.dts), [MT6735 reserved-memory DTS](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/arch/arm/boot/dts/mt6735.dtsi), [reserved-memory allocator](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/drivers/of/of_reserved_mem.c), [MediaTek consys callback](https://github.com/almondnguyen/android_kernel_samsung_grandppltedx/blob/lineage-15.1/drivers/misc/mediatek/connectivity/common/conn_soc/mt6735/mtk_wcn_consys_hw.c).

The live `/proc/iomem` snapshot is retained outside git at `/mnt/d/J2-iOS-audit-20261027/runtime-iomem-20261028.txt`. It reports `80000000-9f5bffff : System RAM`, containing the selected 64 MiB interval. A fresh, read-only root ADB capture of the running J2 Prime kernel log resolves the dynamic allocation exactly: `consys-reserve-memory : 0x7f800000 - 0x7f8fffff (0x100000)`. The memblock reserved list independently reports the same range. The candidate starts at `0x80000000`, 7 MiB after consys ends, and is outside the DTB allocation window `[0x40000000,0x80000000)`. The log also reports ATF memory reserved at `0x9f5c0000-0x9fffffff`, immediately above the `/proc/iomem` System RAM end; it does not overlap the candidate. Raw read-only snapshots are retained outside git at `/mnt/d/J2-iOS-audit-20261027/runtime-dmesg-20261028.txt`, `runtime-iomem-20261028.txt`, `runtime-memblock-reserved-20261028.txt`, and `runtime-memblock-memory-20261028.txt`. These observations verify the candidate against the current LineageOS boot's allocator state; they do not establish ownership under a different preloader/TrustZone boot path.

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

The script rejects candidate windows outside captured RAM, overlapping static reservations, or intersecting any declared dynamic allocation range. No QEMU ARM64 executable is installed in this environment, and the loader has not been run under emulation or on the handset.

### Assessment

**RAM placement passes the available runtime checks; kernel handoff remains unverified.** Windows Minimal ADB and Fastboot at `C:\Program Files (x86)\Minimal ADB and Fastboot` sees serial `4200def9d8929447`, product `grandppltedx`, model `SM_G532G`; root read-only ADB captured `/proc/iomem`, the exact consys allocation, and memblock reservations. The device is back in Android (`sys.boot_completed=1`). The packaged temporary Android boot image is at `/mnt/d/J2-iOS-audit-20261027/j2prime-earlyboot-runtime-20261028/J2PRIME-TEMP-FASTBOOT-DO-NOT-FLASH.img` (SHA-256 `d29c188ed1480f8a003faee2bc6c7179994cdfa8b6ebd44db3222d4e140ff274`). It has not been sent to the phone. Linux `fastboot devices` returned no device, and the bundled Windows fastboot did not yield usable device enumeration. No fastboot transport is currently available for a RAM-only `fastboot boot` test. Do not flash this artifact.

No GICv2 interrupt delivery, timer tick, XNU entry execution, console after the jump, or boot beyond earliest XNU startup has been verified. This is an early-boot kernel diagnostic, not iOS userspace. A safe runtime test now needs a validated RAM-only MT6737 launch mechanism (the prior MTK shim color test proves the shim can execute, but not that this XNU package is reachable through it); Android fastboot is not that mechanism on the currently observed device connection.
