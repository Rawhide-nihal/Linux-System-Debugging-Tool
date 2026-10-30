#include <stdio.h>
#include <signal.h>
#include <unistd.h>

int main(void)
{
    printf("About to terminate with SIGTERM.\n");
    fflush(stdout);
    raise(SIGTERM);
    return 0;
}
