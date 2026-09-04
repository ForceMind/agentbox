#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static int exact_descriptor_inventory(int launch) {
    int descriptor;
    for (descriptor = 3; descriptor < 64; ++descriptor) {
        int expected = descriptor == 5 || (launch == 0 && descriptor == 4);
        errno = 0;
        if ((fcntl(descriptor, F_GETFD) >= 0) != expected || (!expected && errno != EBADF)) {
            return -1;
        }
    }
    return 0;
}

static int valid_digest(const char *value) {
    size_t index;
    if (strlen(value) != 64U) {
        return 0;
    }
    for (index = 0; index < 64U; ++index) {
        if (!((value[index] >= '0' && value[index] <= '9') ||
              (value[index] >= 'a' && value[index] <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static int valid_parent_bootstrap(const char *path) {
    char prefix[32];
    struct stat status;
    int length = snprintf(prefix, sizeof(prefix), "/proc/%ld/fd/", (long)getppid());
    int fd;
    const char *cursor;
    if (length < 0 || (size_t)length >= sizeof(prefix) ||
        strncmp(path, prefix, (size_t)length) != 0) {
        return 0;
    }
    cursor = path + (size_t)length;
    if (*cursor == '\0') {
        return 0;
    }
    while (*cursor != '\0') {
        if (*cursor < '0' || *cursor > '9') {
            return 0;
        }
        ++cursor;
    }
    fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &status) != 0 || !S_ISREG(status.st_mode) ||
        (status.st_mode & (S_IWGRP | S_IWOTH)) != 0 ||
        (status.st_mode & (S_IXUSR | S_IXGRP | S_IXOTH)) == 0) {
        if (fd >= 0) {
            (void)close(fd);
        }
        return 0;
    }
    return close(fd) == 0;
}

int main(int argc, char **argv) {
    int index;
    int attach_shape;
    int launch_shape;
    const struct timespec hold = {0, 200000000L};
    attach_shape = argc == 8 && strcmp(argv[0], "tmux") == 0 && strcmp(argv[1], "-S") == 0 &&
                   strncmp(argv[2], "/proc/self/fd/4/", 16U) == 0 &&
                   strcmp(argv[3], "-f") == 0 && strcmp(argv[4], "/proc/self/fd/5") == 0 &&
                   strcmp(argv[5], "attach-session") == 0 && strcmp(argv[6], "-t") == 0 &&
                   argv[7][0] == '=';
    launch_shape = argc == 14 && strcmp(argv[0], "tmux") == 0 &&
                   strcmp(argv[1], "-S") == 0 &&
                   strncmp(argv[2], "/run/agentbox-waw/tmux/", 23U) == 0 &&
                   strcmp(argv[3], "-f") == 0 && strcmp(argv[4], "/proc/self/fd/5") == 0 &&
                   strcmp(argv[5], "new-session") == 0 && strcmp(argv[6], "-d") == 0 &&
                   strcmp(argv[7], "-s") == 0 &&
                   strncmp(argv[8], "agentbox-waw-claude-", 20U) == 0 &&
                   valid_parent_bootstrap(argv[9]) != 0 &&
                   strcmp(argv[10], "--workspace-hash") == 0 &&
                   valid_digest(argv[11]) != 0 &&
                   strcmp(argv[12], "--agent-type") == 0 && strcmp(argv[13], "claude") == 0;
    if ((!attach_shape && !launch_shape) || exact_descriptor_inventory(launch_shape) != 0 ||
        (attach_shape &&
         (!isatty(STDIN_FILENO) || prctl(PR_GET_NO_NEW_PRIVS, 0UL, 0UL, 0UL, 0UL) != 1))) {
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
