#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <time.h>
#include <unistd.h>

static int exact_descriptor_inventory(void) {
    int descriptor;
    for (descriptor = 3; descriptor < 64; ++descriptor) {
        int expected = descriptor == 4 || descriptor == 5;
        errno = 0;
        if ((fcntl(descriptor, F_GETFD) >= 0) != expected || (!expected && errno != EBADF)) {
            return -1;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    int index;
    const struct timespec hold = {0, 200000000L};
    if (argc != 8 || strcmp(argv[0], "tmux") != 0 || strcmp(argv[1], "-S") != 0 ||
        strncmp(argv[2], "/proc/self/fd/4/", 16U) != 0 || strcmp(argv[3], "-f") != 0 ||
        strcmp(argv[4], "/proc/self/fd/5") != 0 || strcmp(argv[5], "attach-session") != 0 ||
        strcmp(argv[6], "-t") != 0 || argv[7][0] != '=' || !isatty(STDIN_FILENO) ||
        prctl(PR_GET_NO_NEW_PRIVS, 0UL, 0UL, 0UL, 0UL) != 1 ||
        exact_descriptor_inventory() != 0) {
        return 90;
    }
    for (index = 0; index < argc; ++index) {
        if (printf("ARG%d=%s\r\n", index, argv[index]) < 0) {
            return 91;
        }
    }
    (void)nanosleep(&hold, NULL);
    return 23;
}
