#include <stdio.h>

int main(void) {
    int a = 100;
    int b = 0;
    printf("[*] Dividing by zero...\n");
    int c = a / b;
    printf("Result: %d\n", c);
    return 0;
}
