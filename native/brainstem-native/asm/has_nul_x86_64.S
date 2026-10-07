.text
.globl brainstem_has_nul_asm
.type brainstem_has_nul_asm,@function
# System V x86-64 ABI: rdi=data, rsi=length. This deliberately tiny routine
# is selected only on Linux x86-64; every other platform uses the C++ fallback.
brainstem_has_nul_asm:
    xor %rax, %rax
    test %rsi, %rsi
    je .not_found
.scan:
    cmpb $0, (%rdi,%rax,1)
    je .found
    inc %rax
    cmp %rsi, %rax
    jb .scan
.not_found:
    xor %eax, %eax
    ret
.found:
    mov $1, %eax
    ret
.size brainstem_has_nul_asm, .-brainstem_has_nul_asm
