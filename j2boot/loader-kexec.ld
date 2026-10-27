ENTRY(_start)
SECTIONS {
  . = 0x84004000;
  .text : { *(.text.start) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  . = ALIGN(16);
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  . = ALIGN(4096);
  _payload = .;
  _end = .;
  /DISCARD/ : { *(.comment*) *(.note*) *(.eh_frame*) }
}
