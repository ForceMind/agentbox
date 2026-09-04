#define _GNU_SOURCE

#include "waw_native.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
#include <poll.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#endif

int agentbox_waw_is_hex_digest(const char *value) {
    size_t index;
    if (value == NULL ||
        strnlen(value, (size_t)AGENTBOX_WAW_WORKSPACE_HASH_BYTES + 1U) !=
            (size_t)AGENTBOX_WAW_WORKSPACE_HASH_BYTES) {
        return 0;
    }
    for (index = 0; index < (size_t)AGENTBOX_WAW_WORKSPACE_HASH_BYTES; ++index) {
        const char current = value[index];
        if (!((current >= '0' && current <= '9') || (current >= 'a' && current <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

int agentbox_waw_parse_agent(const char *value, enum agentbox_waw_agent_type *agent) {
    if (value == NULL || agent == NULL) {
        errno = EINVAL;
        return -1;
    }
    if (strcmp(value, "claude") == 0) {
        *agent = AGENTBOX_WAW_AGENT_CLAUDE;
        return 0;
    }
    if (strcmp(value, "codex") == 0) {
        *agent = AGENTBOX_WAW_AGENT_CODEX;
        return 0;
    }
    errno = EINVAL;
    return -1;
}

const char *agentbox_waw_agent_name(enum agentbox_waw_agent_type agent) {
    if (agent == AGENTBOX_WAW_AGENT_CLAUDE) {
        return "claude";
    }
    if (agent == AGENTBOX_WAW_AGENT_CODEX) {
        return "codex";
    }
    return NULL;
}

int agentbox_waw_set_cloexec(int fd, int enabled) {
    int flags = fcntl(fd, F_GETFD);
    if (flags < 0) {
        return -1;
    }
    if (enabled != 0) {
        flags |= FD_CLOEXEC;
    } else {
        flags &= ~FD_CLOEXEC;
    }
    return fcntl(fd, F_SETFD, flags);
}

int agentbox_waw_duplicate_high(int fd) {
    return fcntl(fd, F_DUPFD_CLOEXEC, (int)AGENTBOX_WAW_NATIVE_MAX_OPEN_FDS);
}

int agentbox_waw_close_except(const int *kept, size_t count) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK) && defined(SYS_close_range)
    int ordered[16];
    size_t ordered_count = 0;
    size_t index;
    unsigned int first = 3U;
    if (count > sizeof(ordered) / sizeof(ordered[0])) {
        errno = E2BIG;
        return -1;
    }
    for (index = 0; index < count; ++index) {
        size_t position;
        if (kept[index] < 3) {
            continue;
        }
        position = ordered_count;
        while (position > 0U && ordered[position - 1U] > kept[index]) {
            ordered[position] = ordered[position - 1U];
            --position;
        }
        if ((position > 0U && ordered[position - 1U] == kept[index]) ||
            (position < ordered_count && ordered[position] == kept[index])) {
            continue;
        }
        ordered[position] = kept[index];
        ++ordered_count;
    }
    for (index = 0; index < ordered_count; ++index) {
        const unsigned int preserve = (unsigned int)ordered[index];
        if (first < preserve && syscall(SYS_close_range, first, preserve - 1U, 0U) != 0L) {
            return -1;
        }
        first = preserve + 1U;
    }
    if (syscall(SYS_close_range, first, UINT_MAX, 0U) != 0L) {
        return -1;
    }
    return 0;
#else
    struct rlimit limit;
    unsigned long maximum;
    unsigned long candidate;
    if (getrlimit(RLIMIT_NOFILE, &limit) != 0) {
        return -1;
    }
    maximum = limit.rlim_cur == RLIM_INFINITY ? 4096UL : (unsigned long)limit.rlim_cur;
    if (maximum > 65536UL) {
        maximum = 65536UL;
    }
    for (candidate = 3UL; candidate < maximum; ++candidate) {
        size_t index;
        int preserve = 0;
        if (candidate > (unsigned long)INT_MAX) {
            break;
        }
        for (index = 0; index < count; ++index) {
            if (kept[index] == (int)candidate) {
                preserve = 1;
                break;
            }
        }
        if (preserve == 0 && close((int)candidate) != 0 && errno != EBADF) {
            return -1;
        }
    }
    return 0;
#endif
}

static int set_limit(int resource, rlim_t soft, rlim_t hard) {
    struct rlimit limit;
    limit.rlim_cur = soft;
    limit.rlim_max = hard;
    return setrlimit(resource, &limit);
}

int agentbox_waw_apply_basic_limits(void) {
    struct rlimit current;
    rlim_t nofile;
    rlim_t stack;
    if (set_limit(RLIMIT_CORE, 0, 0) != 0) {
        return -1;
    }
    if (getrlimit(RLIMIT_NOFILE, &current) != 0) {
        return -1;
    }
    nofile = current.rlim_max;
    if (nofile == RLIM_INFINITY || nofile > (rlim_t)AGENTBOX_WAW_NATIVE_MAX_OPEN_FDS) {
        nofile = (rlim_t)AGENTBOX_WAW_NATIVE_MAX_OPEN_FDS;
    }
    if (set_limit(RLIMIT_NOFILE, nofile, nofile) != 0) {
        return -1;
    }
    if (getrlimit(RLIMIT_STACK, &current) != 0) {
        return -1;
    }
    stack = current.rlim_max;
    if (stack == RLIM_INFINITY || stack > (rlim_t)(8U * 1024U * 1024U)) {
        stack = (rlim_t)(8U * 1024U * 1024U);
    }
    if (set_limit(RLIMIT_STACK, stack, stack) != 0) {
        return -1;
    }
    if (getrlimit(RLIMIT_FSIZE, &current) != 0) {
        return -1;
    }
    if (current.rlim_max == RLIM_INFINITY || current.rlim_max > (rlim_t)(64U * 1024U * 1024U)) {
        if (set_limit(RLIMIT_FSIZE, (rlim_t)(64U * 1024U * 1024U),
                      (rlim_t)(64U * 1024U * 1024U)) != 0) {
            return -1;
        }
    }
    return 0;
}

int agentbox_waw_apply_no_new_privs(void) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    return prctl(PR_SET_NO_NEW_PRIVS, 1UL, 0UL, 0UL, 0UL);
#else
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_pidfd_open(int pid) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK) && defined(SYS_pidfd_open)
    long result = syscall(SYS_pidfd_open, pid, 0U);
    if (result < 0L || result > (long)INT_MAX) {
        if (result > (long)INT_MAX) {
            errno = EOVERFLOW;
        }
        return -1;
    }
    return (int)result;
#else
    (void)pid;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_exec_held(int fd, char *const argv[], char *const envp[]) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    return execveat(fd, "", argv, envp, AT_EMPTY_PATH);
#else
    (void)fd;
    (void)argv;
    (void)envp;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_validate_directory_fd(int fd) {
    struct stat status;
    if (fstat(fd, &status) != 0 || !S_ISDIR(status.st_mode)) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

int agentbox_waw_validate_regular_fd(int fd) {
    struct stat status;
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0 || (flags & O_ACCMODE) != O_RDONLY || fstat(fd, &status) != 0 ||
        !S_ISREG(status.st_mode) || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

int agentbox_waw_validate_executable_fd(int fd) {
    struct stat status;
    if (agentbox_waw_validate_regular_fd(fd) != 0 || fstat(fd, &status) != 0 ||
        (status.st_mode & (S_IXUSR | S_IXGRP | S_IXOTH)) == 0) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

int agentbox_waw_validate_path_directory_fd(int fd) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    int flags;
    if (agentbox_waw_validate_directory_fd(fd) != 0) {
        return -1;
    }
    flags = fcntl(fd, F_GETFL);
    if (flags < 0 || (flags & O_PATH) != O_PATH) {
        errno = EINVAL;
        return -1;
    }
    return 0;
#else
    (void)fd;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_validate_seqpacket_fd(int fd) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    int socket_type = 0;
    int socket_domain = 0;
    socklen_t size = (socklen_t)sizeof(socket_type);
    socklen_t domain_size = (socklen_t)sizeof(socket_domain);
    struct sockaddr_storage peer;
    socklen_t peer_size = (socklen_t)sizeof(peer);
    if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &socket_type, &size) != 0 ||
        size != (socklen_t)sizeof(socket_type) || socket_type != SOCK_SEQPACKET ||
        getsockopt(fd, SOL_SOCKET, SO_DOMAIN, &socket_domain, &domain_size) != 0 ||
        domain_size != (socklen_t)sizeof(socket_domain) || socket_domain != AF_UNIX ||
        getpeername(fd, (struct sockaddr *)&peer, &peer_size) != 0 || peer.ss_family != AF_UNIX) {
        errno = EINVAL;
        return -1;
    }
    return 0;
#else
    (void)fd;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_read_exact(int fd, void *buffer, size_t size) {
    size_t offset = 0;
    unsigned char *output = (unsigned char *)buffer;
    while (offset < size) {
        ssize_t received = read(fd, output + offset, size - offset);
        if (received == 0) {
            errno = EPIPE;
            return -1;
        }
        if (received < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        offset += (size_t)received;
    }
    return 0;
}

int agentbox_waw_write_exact(int fd, const void *buffer, size_t size) {
    size_t offset = 0;
    const unsigned char *input = (const unsigned char *)buffer;
    while (offset < size) {
        ssize_t written = write(fd, input + offset, size - offset);
        if (written < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        offset += (size_t)written;
    }
    return 0;
}

int agentbox_waw_confirm_exec_timeout(int status_fd, int pidfd, int timeout_ms) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    struct pollfd watched[2];
    unsigned char failure;
    int result;
    watched[0].fd = status_fd;
    watched[0].events = POLLIN | POLLHUP;
    watched[0].revents = 0;
    watched[1].fd = pidfd;
    watched[1].events = POLLIN;
    watched[1].revents = 0;
    if (timeout_ms <= 0 || timeout_ms > (int)AGENTBOX_WAW_READY_DEADLINE_MS) {
        errno = EINVAL;
        return -1;
    }
    result = poll(watched, 2U, timeout_ms);
    if (result <= 0 || (watched[1].revents & (POLLIN | POLLHUP | POLLERR)) != 0 ||
        (watched[0].revents & (POLLIN | POLLHUP | POLLERR)) == 0) {
        errno = result == 0 ? ETIMEDOUT : EPROTO;
        return -1;
    }
    result = (int)read(status_fd, &failure, sizeof(failure));
    if (result != 0) {
        errno = EPROTO;
        return -1;
    }
    watched[1].revents = 0;
    if (poll(&watched[1], 1U, 0) != 0) {
        errno = EPROTO;
        return -1;
    }
    return 0;
#else
    (void)status_fd;
    (void)pidfd;
    (void)timeout_ms;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_confirm_exec(int status_fd, int pidfd) {
    return agentbox_waw_confirm_exec_timeout(status_fd, pidfd,
                                             (int)AGENTBOX_WAW_READY_DEADLINE_MS);
}

int agentbox_waw_send_ready(int fd) {
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    static const unsigned char frame[AGENTBOX_WAW_READY_FRAME_BYTES] = {
        'A', 'W', 'R', '1', AGENTBOX_WAW_READY_VERSION, AGENTBOX_WAW_READY_STATUS_RUNNING, 0U, 0U};
    ssize_t sent = send(fd, frame, sizeof(frame), MSG_DONTWAIT | MSG_NOSIGNAL);
    return sent == (ssize_t)sizeof(frame) ? 0 : -1;
#else
    (void)fd;
    errno = ENOTSUP;
    return -1;
#endif
}

int agentbox_waw_wait_child(int pid, int pidfd) {
    int status = 0;
#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)
    struct pollfd watched;
    watched.fd = pidfd;
    watched.events = POLLIN;
    watched.revents = 0;
    while (poll(&watched, 1, -1) < 0) {
        if (errno != EINTR) {
            return 125;
        }
    }
#else
    (void)pidfd;
#endif
    while (waitpid((pid_t)pid, &status, 0) < 0) {
        if (errno != EINTR) {
            return 125;
        }
    }
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 125;
}

void agentbox_waw_terminate_and_reap(int pid, int pidfd) {
    int status;
    if (pid > 0) {
        (void)kill((pid_t)pid, SIGKILL);
        while (waitpid((pid_t)pid, &status, 0) < 0 && errno == EINTR) {
        }
    }
    if (pidfd >= 0) {
        (void)close(pidfd);
    }
}
