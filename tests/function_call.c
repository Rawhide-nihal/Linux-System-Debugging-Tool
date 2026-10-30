#include <stdio.h>

static int add(int x, int y)
{
    int sum = x + y;
    return sum;
}

int main(void)
{
    int a = 10;
    int b = 20;
    int c = add(a, b);
    printf("Result of add(%d, %d) is %d\n", a, b, c);
    return 0;
}
