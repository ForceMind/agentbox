#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/types.h>
#include <termios.h>
#include <unistd.h>

extern char **environ;

static int required_environment(void) {
    static const char *const names[] = {
        "HOME=",          "XDG_CONFIG_HOME=", "XDG_CACHE_HOME=", "XDG_DATA_HOME=",
        "XDG_STATE_HOME=", "TMPDIR=",          "PATH=",           "LANG=",
        "LC_CTYPE=",      "TERM=",
    };
    size_t required_index;
    size_t count = 0;
    int state_count = 0;
    char **item;
    for (item = environ; *item != NULL; ++item) {
        ++count;
        if (strncmp(*item, "TMUX=", 5U) == 0 || strncmp(*item, "TMUX_PANE=", 10U) == 0 ||
            strstr(*item, "TOKEN=") != NULL || strstr(*item, "API_KEY=") != NULL) {
            return -1;
        }
        if (strncmp(*item, "CLAUDE_CONFIG_DIR=", 18U) == 0 ||
            strncmp(*item, "CODEX_HOME=", 11U) == 0) {
            ++state_count;
        }
    }
    if (count != 11U || state_count != 1) {
        return -1;
    }
    for (required_index = 0; required_index < sizeof(names) / sizeof(names[0]);
         ++required_index) {
        int found = 0;
        for (item = environ; *item != NULL; ++item) {
            if (strncmp(*item, names[required_index], strlen(names[required_index])) == 0) {
                found = 1;
                break;
            }
        }
        if (found == 0) {
            return -1;
        }
    }
    return 0;
}

static int show_size(const char *prefix) {
    struct winsize geometry;
    if (ioctl(STDIN_FILENO, TIOCGWINSZ, &geometry) != 0) {
        return -1;
    }
    return printf("%s %u %u\r\n", prefix, (unsigned int)geometry.ws_col,
                  (unsigned int)geometry.ws_row) < 0
               ? -1
               : 0;
}

static int exact_descriptor_inventory(void) {
    int descriptor;
    for (descriptor = 3; descriptor < 64; ++descriptor) {
        errno = 0;
        if (fcntl(descriptor, F_GETFD) >= 0 || errno != EBADF) {
            return -1;
        }
    }
    return 0;
}

static int bounded_limits(void) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_CORE, &limit) != 0 || limit.rlim_cur != 0 || limit.rlim_max != 0 ||
        getrlimit(RLIMIT_NOFILE, &limit) != 0 || limit.rlim_cur > 64 || limit.rlim_max > 64 ||
        getrlimit(RLIMIT_STACK, &limit) != 0 || limit.rlim_cur > 8U * 1024U * 1024U ||
        limit.rlim_max > 8U * 1024U * 1024U) {
        return -1;
    }
    return 0;
}

static int capabilities_are_empty(void) {
    FILE *status = fopen("/proc/self/status", "r");
    char line[256];
    unsigned long long permitted = 1U;
    unsigned long long effective = 1U;
    int found = 0;
    int close_result;
    if (status == NULL) {
        return -1;
    }
    while (fgets(line, sizeof(line), status) != NULL) {
        unsigned long long value;
        if (sscanf(line, "CapPrm:%llx", &value) == 1) {
            permitted = value;
            ++found;
        } else if (sscanf(line, "CapEff:%llx", &value) == 1) {
            effective = value;
            ++found;
        }
    }
    close_result = fclose(status);
    return found == 2 && close_result == 0 && permitted == 0U && effective == 0U ? 0 : -1;
}

static int expect_open_denied(const char *path) {
    int descriptor;
    errno = 0;
    descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor >= 0) {
        (void)close(descriptor);
        return -1;
    }
    return errno == EACCES || errno == ENOENT || errno == ENOTDIR ? 0 : -1;
}

static int expect_file(const char *path, const char *expected) {
    char buffer[16];
    int descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    ssize_t received;
    if (descriptor < 0) {
        return -1;
    }
    received = read(descriptor, buffer, sizeof(buffer));
    (void)close(descriptor);
    return received == (ssize_t)strlen(expected) &&
                   memcmp(buffer, expected, (size_t)received) == 0
               ? 0
               : -1;
}

static int expect_writable_directory(const char *directory) {
    char path[PATH_MAX];
    int length = snprintf(path, sizeof(path), "%s/.native-write-check", directory);
    int descriptor;
    if (length < 0 || (size_t)length >= sizeof(path)) {
        return -1;
    }
    descriptor = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (descriptor < 0) {
        return -1;
    }
    {
        ssize_t written = write(descriptor, "ok", 2U);
        int close_result = close(descriptor);
        if (written != 2 || close_result != 0) {
            (void)unlink(path);
            return -1;
        }
    }
    if (unlink(path) != 0) {
        return -1;
    }
    return 0;
}

static int expect_write_denied(const char *path) {
    int descriptor;
    errno = 0;
    descriptor = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor >= 0) {
        (void)close(descriptor);
        return -1;
    }
    return errno == EACCES || errno == EROFS ? 0 : -1;
}

static void *thread_entry(void *value) {
    return value;
}

static int threads_and_clone_policy(void) {
    pthread_t thread;
    void *result = NULL;
    void *expected = (void *)&thread;
    if (pthread_create(&thread, NULL, thread_entry, expected) != 0 ||
        pthread_join(thread, &result) != 0 || result != expected) {
        return -1;
    }
#ifdef SYS_clone3
    errno = 0;
    if (syscall(SYS_clone3, NULL, 0U) != -1 || errno != ENOSYS) {
        return -1;
    }
#endif
#ifdef SYS_clone
    errno = 0;
    if (syscall(SYS_clone, (unsigned long)(CLONE_NEWUSER | CLONE_NEWNS | SIGCHLD), NULL,
                NULL, NULL, 0UL) != -1 ||
        errno != EPERM) {
        return -1;
    }
#endif
    return 0;
}

static int isolation_is_enforced(const char *agent) {
    char executable[PATH_MAX];
    char socket_path[sizeof(((struct sockaddr_un *)0)->sun_path)];
    struct sockaddr_un address;
    int descriptor;
    ssize_t length;
    FILE *record;
    unsigned long long host_namespaces[4];
    static const char *const namespace_paths[] = {
        "/proc/self/ns/user", "/proc/self/ns/mnt", "/proc/self/ns/pid", "/proc/self/ns/ipc"};
    size_t namespace_index;
    int scanned;
    int record_close;
    const char *other_home = strcmp(agent, "claude") == 0
                                 ? "/var/lib/agentbox-waw/vendor-homes/codex/forbidden-canary"
                                 : "/var/lib/agentbox-waw/vendor-homes/claude/forbidden-canary";
    const char *home = getenv("HOME");
    const char *temporary = getenv("TMPDIR");
    const char *policy = strcmp(agent, "claude") == 0
                             ? "/etc/claude-code/policy-mount-canary"
                             : "/etc/codex/policy-mount-canary";
    char home_canary[PATH_MAX];
    char temp_canary[PATH_MAX];
    if (home == NULL || temporary == NULL ||
        snprintf(home_canary, sizeof(home_canary), "%s/.home-mount-canary", home) < 0 ||
        snprintf(temp_canary, sizeof(temp_canary), "%s/.temp-mount-canary", temporary) < 0 ||
        expect_file(home_canary, "home\n") != 0 || expect_file(temp_canary, "temp\n") != 0 ||
        expect_file(policy, "policy\n") != 0 || expect_write_denied(policy) != 0 ||
        expect_writable_directory(home) != 0 ||
        expect_writable_directory(temporary) != 0 || geteuid() != 1000U ||
        getegid() != 1000U || getpid() <= 1 || threads_and_clone_policy() != 0 ||
        expect_open_denied("/var/lib/agentbox-waw/runtime-epoch-v1") != 0 ||
        expect_open_denied(other_home) != 0 ||
        expect_open_denied(
            "/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1/canary") != 0 ||
        expect_open_denied("/run/agentbox-waw/tmux/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.sock") !=
            0 ||
        expect_open_denied("/root") != 0) {
        return -1;
    }
    length = readlink("/proc/1/exe", executable, sizeof(executable) - 1U);
    if (length <= 0 || (size_t)length >= sizeof(executable)) {
        return -1;
    }
    executable[(size_t)length] = '\0';
    if (strstr(executable, "agentbox-waw-bridge") == NULL) {
        return -1;
    }
    record = fopen(".host-namespaces", "r");
    if (record == NULL) {
        return -1;
    }
    scanned = fscanf(record, "%llu %llu %llu %llu", &host_namespaces[0],
                     &host_namespaces[1], &host_namespaces[2], &host_namespaces[3]);
    record_close = fclose(record);
    if (scanned != 4 || record_close != 0) {
        return -1;
    }
    for (namespace_index = 0;
         namespace_index < sizeof(namespace_paths) / sizeof(namespace_paths[0]);
         ++namespace_index) {
        struct stat namespace_status;
        if (stat(namespace_paths[namespace_index], &namespace_status) != 0 ||
            (unsigned long long)namespace_status.st_ino == host_namespaces[namespace_index]) {
            return -1;
        }
    }
    errno = 0;
    if (syscall(SYS_setns, -1, 0) != -1 || errno != EPERM) {
        return -1;
    }
    errno = 0;
    if (syscall(SYS_mount, "none", "/", "none", 0UL, NULL) != -1 || errno != EPERM) {
        return -1;
    }
#ifdef SYS_ptrace
    errno = 0;
    if (syscall(SYS_ptrace, 0L, 0L, 0L, 0L) != -1 || errno != EPERM) {
        return -1;
    }
#endif
#ifdef SYS_process_vm_readv
    errno = 0;
    if (syscall(SYS_process_vm_readv, 1L, NULL, 0UL, NULL, 0UL, 0UL) != -1 ||
        errno != EPERM) {
        return -1;
    }
#endif
#ifdef SYS_bpf
    errno = 0;
    if (syscall(SYS_bpf, 0L, NULL, 0UL) != -1 || errno != EPERM) {
        return -1;
    }
#endif
#ifdef SYS_perf_event_open
    errno = 0;
    if (syscall(SYS_perf_event_open, NULL, 0L, -1L, -1L, 0UL) != -1 || errno != EPERM) {
        return -1;
    }
#endif
#ifdef SYS_keyctl
    errno = 0;
    if (syscall(SYS_keyctl, 0L, 0L, 0L, 0L, 0L) != -1 || errno != EPERM) {
        return -1;
    }
#endif
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    (void)snprintf(socket_path, sizeof(socket_path), "/run/agentbox-waw/workspace-control.sock");
    (void)memcpy(address.sun_path, socket_path, strlen(socket_path) + 1U);
    descriptor = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (descriptor < 0) {
        return -1;
    }
    errno = 0;
    if (connect(descriptor, (struct sockaddr *)&address, sizeof(address)) == 0 ||
        (errno != EACCES && errno != ENOENT && errno != ENOTSOCK && errno != ECONNREFUSED)) {
        (void)close(descriptor);
        return -1;
    }
    (void)close(descriptor);
    return 0;
}

static int spawn_stubborn_descendant(void) {
    pid_t child = fork();
    if (child < 0) {
        return -1;
    }
    if (child == 0) {
        pid_t grandchild;
        if (setsid() < 0) {
            _exit(95);
        }
        grandchild = fork();
        if (grandchild < 0) {
            _exit(95);
        }
        if (grandchild > 0) {
            _exit(0);
        }
        (void)signal(SIGTERM, SIG_IGN);
        for (;;) {
            (void)pause();
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    char line[256];
    int no_new_privs;
    if (argc != 1 || (strcmp(argv[0], "claude") != 0 && strcmp(argv[0], "codex") != 0) ||
        required_environment() != 0 || !isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) ||
        getsid(0) != getpid() || tcgetsid(STDIN_FILENO) != getpid() ||
        exact_descriptor_inventory() != 0 || bounded_limits() != 0 ||
        capabilities_are_empty() != 0 ||
        isolation_is_enforced(argv[0]) != 0) {
        return 90;
    }
    no_new_privs = prctl(PR_GET_NO_NEW_PRIVS, 0UL, 0UL, 0UL, 0UL);
    if (no_new_privs != 1 || setvbuf(stdout, NULL, _IONBF, 0U) != 0 ||
        printf("READY %s\r\n", argv[0]) < 0 || show_size("SIZE") != 0) {
        return 91;
    }
    while (fgets(line, sizeof(line), stdin) != NULL) {
        if (strcmp(line, "size\n") == 0 || strcmp(line, "size\r\n") == 0) {
            if (show_size("SIZE") != 0) {
                return 92;
            }
        } else if (strcmp(line, "pid\n") == 0 || strcmp(line, "pid\r\n") == 0) {
            if (printf("PID %ld\r\n", (long)getpid()) < 0) {
                return 92;
            }
        } else if (strcmp(line, "spawn\n") == 0 || strcmp(line, "spawn\r\n") == 0) {
            if (spawn_stubborn_descendant() != 0 || printf("SPAWNED\r\n") < 0) {
                return 92;
            }
        } else if (strcmp(line, "controls\n") == 0 || strcmp(line, "controls\r\n") == 0) {
            if (printf("\033]52;c;FORBIDDEN-CLIPBOARD\a"
                       "\033Ptmux;\033\033]52;c;FORBIDDEN-PASSTHROUGH\a\033\\"
                       "CONTROL-DONE\r\n") < 0) {
                return 92;
            }
        } else if (strcmp(line, "tail\n") == 0 || strcmp(line, "tail\r\n") == 0) {
            size_t index;
            for (index = 0; index < 2048U; ++index) {
                if (printf("TAIL %04zu 0123456789abcdef0123456789abcdef\r\n", index) < 0) {
                    return 92;
                }
            }
            if (printf("TAIL-END\r\n") < 0) {
                return 92;
            }
            return 7;
        } else if (strcmp(line, "exit7\n") == 0 || strcmp(line, "exit7\r\n") == 0) {
            return 7;
        } else if (printf("ECHO %s", line) < 0) {
            return 93;
        }
    }
    return ferror(stdin) != 0 ? 94 : 0;
}
