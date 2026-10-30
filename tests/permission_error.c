#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/stat.h>

static int run_permission_test(const char *file)
{
    int fd = open(file, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) {
        chmod(file, 0600);
        unlink(file);
        fd = open(file, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (fd < 0) {
            return -2;
        }
    }
    close(fd);

    if (chmod(file, 0000) < 0) {
        unlink(file);
        return -2;
    }

    fd = open(file, O_RDONLY);
    if (fd < 0) {
        int saved_errno = errno;
        printf("permission test open() failed\n");
        printf("errno      : %d\n", saved_errno);
        printf("error      : %s\n", strerror(saved_errno));
        chmod(file, 0600);
        unlink(file);
        errno = saved_errno;
        return -1;
    }

    close(fd);
    chmod(file, 0600);
    unlink(file);
    return 0;
}

int main(void)
{
    /* Try local tests/ directory first; if the underlying filesystem
       (e.g. a mounted non-POSIX volume) does not enforce chmod 0000,
       fall back to /tmp which is a native Linux POSIX filesystem. */
    const char *local_file = "tests/permission_denied_target.txt";
    int rc = run_permission_test(local_file);
    if (rc == -1) {
        return 1;
    }

    const char *tmp_file = "/tmp/ldst_permission_denied_target.txt";
    rc = run_permission_test(tmp_file);
    if (rc == -1) {
        return 1;
    }

    printf("permission test: open() succeeded unexpectedly (possibly running as root)\n");
    return 0;
}
