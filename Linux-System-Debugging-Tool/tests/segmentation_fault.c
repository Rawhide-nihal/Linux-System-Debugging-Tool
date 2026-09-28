#include <stdio.h>

int main(void)
{
    printf("About to trigger a controlled segmentation fault.\n");
    fflush(stdout);

    int *ptr = NULL;
    *ptr = 42;

    return 0;
}
