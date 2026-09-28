#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/stat.h>

int main(void)
{
    const char *file = "tests/permission_denied_target.txt";
    unlink(file);

    int fd = open(file, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) {
        printf("setup failed: %s\n", strerror(errno));
        return 1;
    }
    close(fd);

    if (chmod(file, 0000) < 0) {
        printf("chmod failed: %s\n", strerror(errno));
        unlink(file);
        return 1;
    }

    fd = open(file, O_RDONLY);
    if (fd < 0) {
        printf("permission test open() failed\n");
        printf("errno      : %d\n", errno);
        printf("error      : %s\n", strerror(errno));
        chmod(file, 0600);
        unlink(file);
        return 1;
    }

    close(fd);
    chmod(file, 0600);
    unlink(file);
    return 0;
}
