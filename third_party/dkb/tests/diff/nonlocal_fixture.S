// Authored AArch64 ABI fixture. No game code or data.
.text
.global fixture
fixture:
    stp x29, x30, [sp, #-32]!
    stp x19, x20, [sp, #16]
    mov x29, sp
    mov x19, x0
    mov x20, x1
    bl fixture_setjmp
    cbnz w0, resumed
    mov x0, x19
    mov x1, x20
    bl nested
    brk #1
resumed:
    add w0, w0, #7
    ldp x19, x20, [sp, #16]
    ldp x29, x30, [sp], #32
    ret
.org 0x100
nested:
    stp x29, x30, [sp, #-32]!
    stp x19, x20, [sp, #16]
    mov x29, sp
    mov x19, x0
    mov x20, x1
    add x0, x0, #256
    bl fixture_setjmp
    cbnz w0, invalid
    mov x0, x19
    mov x1, x20
    mov x19, #123
    mov x29, #456
    fmov d8, x19
    b fixture_longjmp
invalid:
    brk #2
.org 0x200
fixture_setjmp:
    stp x19, x20, [x0]
    stp x21, x22, [x0, #16]
    stp x23, x24, [x0, #32]
    stp x25, x26, [x0, #48]
    stp x27, x28, [x0, #64]
    stp x29, x30, [x0, #80]
    mov x2, sp
    str x2, [x0, #96]
    stp d8, d9, [x0, #112]
    stp d10, d11, [x0, #128]
    stp d12, d13, [x0, #144]
    stp d14, d15, [x0, #160]
    mov x0, #0
    ret
.org 0x300
fixture_longjmp:
    ldp x19, x20, [x0]
    ldp x21, x22, [x0, #16]
    ldp x23, x24, [x0, #32]
    ldp x25, x26, [x0, #48]
    ldp x27, x28, [x0, #64]
    ldp x29, x30, [x0, #80]
    ldr x2, [x0, #96]
    mov sp, x2
    ldp d8, d9, [x0, #112]
    ldp d10, d11, [x0, #128]
    ldp d12, d13, [x0, #144]
    ldp d14, d15, [x0, #160]
    cmp w1, #0
    csinc w0, w1, wzr, ne
    br x30
