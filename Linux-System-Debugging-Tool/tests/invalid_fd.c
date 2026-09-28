#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    char buffer[8];
    ssize_t result = read(-1, buffer, sizeof(buffer));

    if (result == -1) {
        printf("read() failed\n");
        printf("errno      : %d\n", errno);
        printf("error      : %s\n", strerror(errno));
        return 1;
    }

    return 0;
}
