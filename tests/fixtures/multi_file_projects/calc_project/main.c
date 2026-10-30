#include <stdio.h>
#include "calc.h"

int main(void) {
    int x = 10;
    int y = 20;
    int sum = add(x, y);
    int prod = multiply(x, y);
    printf("Sum: %d, Product: %d\n", sum, prod);
    return 0;
}
