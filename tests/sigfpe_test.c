#include <stdio.h>

int main(void)
{
    printf("Starting arithmetic test...\n");
    volatile int a = 42;
    volatile int b = 0;
    volatile int c = a / b; /* Intentional divide-by-zero to trigger SIGFPE */
    printf("Result: %d\n", c);
    return 0;
}
