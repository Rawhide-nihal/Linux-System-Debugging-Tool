#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

int main(void)
{
    char buffer[100];

    printf("========================================\n");
    printf("     SYSTEM CALL ERROR TEST\n");
    printf("========================================\n");

    printf("\nAttempting read() using an invalid file descriptor...\n");

    /*
     * File descriptor 999 is intentionally invalid.
     * read() should fail and return -1.
     */
    ssize_t result = read(999, buffer, sizeof(buffer));

    if (result == -1)
    {
        printf("\nControlled system-call failure detected.\n");
        printf("System Call : read()\n");
        printf("Return      : %zd\n", result);
        printf("errno       : %d\n", errno);
        printf("Error       : %s\n", strerror(errno));
    }

    printf("\nTest completed.\n");

    return 0;
}
