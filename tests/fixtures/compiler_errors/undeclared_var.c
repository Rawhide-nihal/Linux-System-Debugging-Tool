#include <stdio.h>

int main(void) {
    undeclared_counter = 10;
    printf("%d\n", undeclared_counter);
    return 0;
}
