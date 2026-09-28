#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    int fd = open("missing_file.txt", O_RDONLY);

    if (fd == -1) {
        printf("open() failed\n");
        printf("errno      : %d\n", errno);
        printf("error      : %s\n", strerror(errno));
        return 1;
    }

    close(fd);
    return 0;
}
