#include <stdio.h>

int main(void) {
    int *ptr = NULL;
    printf("[*] Dereferencing null pointer...\n");
    *ptr = 1337;
    return 0;
}
