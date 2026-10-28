ENTRY(_start)
SECTIONS {
  . = 0x40008000;
  .text : { *(.text.start) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  . = ALIGN(16);
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  ASSERT(. <= 0x4000a000, "AArch64 loader exceeds its reserved 8 KiB bootshim window")
  . = 0x4000a000;
  _payload = .;
  _end = .;
  /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
