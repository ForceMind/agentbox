#define _GNU_SOURCE
#define _XOPEN_SOURCE 700

#include "waw_native.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)

#include <sys/prctl.h>

struct relay_buffer {
    unsigned char bytes[AGENTBOX_WAW_RELAY_BUFFER_BYTES];
    size_t begin;
    size_t end;
};

static volatile sig_atomic_t stop_requested = 0;

static void request_stop(int signal_number) {
    (void)signal_number;
    stop_requested = 1;
}

static int install_signal_handlers(void) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = request_stop;
    (void)sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0 || sigaction(SIGINT, &action, NULL) != 0 ||
        sigaction(SIGHUP, &action, NULL) != 0) {
        return -1;
    }
    action.sa_handler = SIG_IGN;
    return sigaction(SIGPIPE, &action, NULL);
}

static uint64_t from_network_u64(const unsigned char *bytes) {
    uint64_t value = 0;
    size_t index;
    for (index = 0; index < 8U; ++index) {
        value = (value << 8U) | (uint64_t)bytes[index];
    }
    return value;
}

static void to_network_u64(unsigned char *bytes, uint64_t value) {
    size_t index;
    for (index = 0; index < 8U; ++index) {
        bytes[7U - index] = (unsigned char)(value & UINT64_C(0xff));
        value >>= 8U;
    }
}

static int validate_config(const struct agentbox_waw_bridge_config *config) {
    const char *agent = agentbox_waw_agent_name((enum agentbox_waw_agent_type)config->agent_type);
    size_t index;
    if (config->magic != AGENTBOX_WAW_BRIDGE_CONFIG_MAGIC ||
        config->abi_version != AGENTBOX_WAW_NATIVE_ABI_VERSION || config->generation == 0U ||
        geteuid() != (uid_t)AGENTBOX_WAW_INNER_UID ||
        getegid() != (gid_t)AGENTBOX_WAW_INNER_GID || getpid() != 1 ||
        config->columns < AGENTBOX_WBR_MIN_COLUMNS ||
        config->columns > AGENTBOX_WBR_MAX_COLUMNS || config->rows < AGENTBOX_WBR_MIN_ROWS ||
        config->rows > AGENTBOX_WBR_MAX_ROWS || agent == NULL ||
        !agentbox_waw_is_hex_digest(config->workspace_hash) ||
        !agentbox_waw_is_hex_digest(config->profile_digest)) {
        errno = EPROTO;
        return -1;
    }
    for (index = 0; index < sizeof(config->reserved); ++index) {
        if (config->reserved[index] != 0U) {
            errno = EPROTO;
            return -1;
        }
    }
    return 0;
}

static int validate_bridge_descriptors(void) {
    return agentbox_waw_validate_seqpacket_fd(AGENTBOX_WAW_BRIDGE_READY_FD) == 0 &&
                   agentbox_waw_validate_directory_fd(AGENTBOX_WAW_BRIDGE_PROJECT_FD) == 0 &&
                   agentbox_waw_validate_directory_fd(AGENTBOX_WAW_BRIDGE_HOME_FD) == 0 &&
                   agentbox_waw_validate_directory_fd(AGENTBOX_WAW_BRIDGE_TEMP_FD) == 0 &&
                   agentbox_waw_validate_executable_fd(
                       AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD) == 0 &&
                   agentbox_waw_validate_directory_fd(AGENTBOX_WAW_BRIDGE_POLICY_FD) == 0 &&
                   agentbox_waw_validate_seqpacket_fd(AGENTBOX_WAW_BRIDGE_WBR_FD) == 0
               ? 0
               : -1;
}

static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL);
    if (flags < 0) {
        return -1;
    }
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

static int open_terminal(const struct agentbox_waw_bridge_config *config, int *master,
                         int *slave) {
    char name[128];
    struct winsize geometry;
    int opened = posix_openpt(O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (opened < 0 || grantpt(opened) != 0 || unlockpt(opened) != 0 ||
        ptsname_r(opened, name, sizeof(name)) != 0) {
        if (opened >= 0) {
            (void)close(opened);
        }
        return -1;
    }
    *slave = open(name, O_RDWR | O_NOCTTY | O_CLOEXEC | O_NOFOLLOW);
    if (*slave < 0) {
        (void)close(opened);
        return -1;
    }
    memset(&geometry, 0, sizeof(geometry));
    geometry.ws_col = config->columns;
    geometry.ws_row = config->rows;
    if (ioctl(*slave, TIOCSWINSZ, &geometry) != 0) {
        (void)close(*slave);
        (void)close(opened);
        return -1;
    }
    *master = opened;
    return 0;
}

static int build_vendor_environment(const struct agentbox_waw_bridge_config *config,
                                    char storage[11][192], char *environment[12]) {
    const char *agent = agentbox_waw_agent_name((enum agentbox_waw_agent_type)config->agent_type);
    const char *state_variable = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE
                                     ? "CLAUDE_CONFIG_DIR"
                                     : "CODEX_HOME";
    const char *state_leaf = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE
                                 ? ".config/claude"
                                 : ".config/codex";
    int lengths[11];
    size_t index;
    if (agent == NULL) {
        return -1;
    }
    lengths[0] = snprintf(storage[0], sizeof(storage[0]), "HOME=/var/lib/agentbox-waw/vendor-homes/%s", agent);
    lengths[1] = snprintf(storage[1], sizeof(storage[1]), "XDG_CONFIG_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.config", agent);
    lengths[2] = snprintf(storage[2], sizeof(storage[2]), "XDG_CACHE_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.cache", agent);
    lengths[3] = snprintf(storage[3], sizeof(storage[3]), "XDG_DATA_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.local/share", agent);
    lengths[4] = snprintf(storage[4], sizeof(storage[4]), "XDG_STATE_HOME=/var/lib/agentbox-waw/vendor-homes/%s/.local/state", agent);
    lengths[5] = snprintf(storage[5], sizeof(storage[5]), "TMPDIR=/run/agentbox-waw/tmp/%s/vendor", config->workspace_hash);
    lengths[6] = snprintf(storage[6], sizeof(storage[6]), "PATH=/usr/bin:/opt/agentbox/current/libexec");
    lengths[7] = snprintf(storage[7], sizeof(storage[7]), "LANG=C.UTF-8");
    lengths[8] = snprintf(storage[8], sizeof(storage[8]), "LC_CTYPE=C.UTF-8");
    lengths[9] = snprintf(storage[9], sizeof(storage[9]), "TERM=xterm-256color");
    lengths[10] = snprintf(storage[10], sizeof(storage[10]), "%s=/var/lib/agentbox-waw/vendor-homes/%s/%s", state_variable, agent, state_leaf);
    for (index = 0; index < 11U; ++index) {
        if (lengths[index] < 0 || (size_t)lengths[index] >= sizeof(storage[index])) {
            return -1;
        }
        environment[index] = storage[index];
    }
    environment[11] = NULL;
    return 0;
}

static void vendor_failure(int status_fd) {
    const unsigned char failed = 1U;
    (void)agentbox_waw_write_exact(status_fd, &failed, sizeof(failed));
    _exit(125);
}

static void vendor_child(const struct agentbox_waw_bridge_config *config, int master, int slave,
                         int status_fd) {
    char environment_storage[11][192];
    char *environment[12];
    const char *agent = agentbox_waw_agent_name((enum agentbox_waw_agent_type)config->agent_type);
    pid_t expected_parent = getppid();
    char *arguments[2];
    int kept[2] = {AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD, status_fd};
    (void)close(master);
    if (expected_parent != 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent || setsid() < 0 ||
        ioctl(slave, TIOCSCTTY, 0) != 0 || dup2(slave, STDIN_FILENO) < 0 ||
        dup2(slave, STDOUT_FILENO) < 0 || dup2(slave, STDERR_FILENO) < 0 ||
        build_vendor_environment(config, environment_storage, environment) != 0 ||
        agentbox_waw_apply_basic_limits() != 0 || agentbox_waw_apply_no_new_privs() != 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD, 1) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0 || agent == NULL) {
        vendor_failure(status_fd);
    }
    arguments[0] = (char *)agent;
    arguments[1] = NULL;
    (void)agentbox_waw_exec_held(AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD, arguments,
                                 environment);
    vendor_failure(status_fd);
}

static int buffer_read(int fd, struct relay_buffer *buffer, int *eof) {
    ssize_t received;
    if (buffer->begin != 0U && buffer->begin == buffer->end) {
        buffer->begin = 0U;
        buffer->end = 0U;
    }
    if (buffer->end == sizeof(buffer->bytes) && buffer->begin > 0U) {
        memmove(buffer->bytes, buffer->bytes + buffer->begin, buffer->end - buffer->begin);
        buffer->end -= buffer->begin;
        buffer->begin = 0U;
    }
    received = read(fd, buffer->bytes + buffer->end, sizeof(buffer->bytes) - buffer->end);
    if (received > 0) {
        buffer->end += (size_t)received;
        return 0;
    }
    if (received == 0 || (received < 0 && errno == EIO)) {
        *eof = 1;
        return 0;
    }
    if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
        return 0;
    }
    return -1;
}

static int buffer_write(int fd, struct relay_buffer *buffer) {
    ssize_t written = write(fd, buffer->bytes + buffer->begin, buffer->end - buffer->begin);
    if (written > 0) {
        buffer->begin += (size_t)written;
        if (buffer->begin == buffer->end) {
            buffer->begin = 0U;
            buffer->end = 0U;
        }
        return 0;
    }
    if (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
        return 0;
    }
    return -1;
}

static int reap_namespace_descendants(void) {
    struct timespec pause = {0, 10000000L};
    int status;
    int attempt;
    (void)kill(-1, SIGTERM);
    for (attempt = 0; attempt < 100; ++attempt) {
        pid_t waited;
        do {
            waited = waitpid(-1, &status, WNOHANG);
        } while (waited > 0);
        if (waited < 0 && errno == ECHILD) {
            return 0;
        }
        (void)nanosleep(&pause, NULL);
    }
    (void)kill(-1, SIGKILL);
    for (attempt = 0; attempt < 100; ++attempt) {
        pid_t waited;
        do {
            waited = waitpid(-1, &status, WNOHANG);
        } while (waited > 0);
        if (waited < 0 && errno == ECHILD) {
            return 0;
        }
        (void)nanosleep(&pause, NULL);
    }
    errno = ETIMEDOUT;
    return -1;
}

static int handle_resize(int master, int wbr, uint64_t generation, uint64_t *last_sequence) {
    unsigned char frame[AGENTBOX_WBR_FRAME_BYTES];
    unsigned char control[CMSG_SPACE(1U)];
    struct iovec vector;
    struct msghdr message;
    struct winsize geometry;
    ssize_t received;
    uint64_t sequence;
    uint64_t supplied_generation;
    uint16_t columns;
    uint16_t rows;
    size_t index;
    memset(&message, 0, sizeof(message));
    memset(control, 0, sizeof(control));
    vector.iov_base = frame;
    vector.iov_len = sizeof(frame);
    message.msg_iov = &vector;
    message.msg_iovlen = 1U;
    message.msg_control = control;
    message.msg_controllen = sizeof(control);
    received = recvmsg(wbr, &message, MSG_DONTWAIT | MSG_CMSG_CLOEXEC);
    if (received != (ssize_t)AGENTBOX_WBR_FRAME_BYTES ||
        (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0 || message.msg_controllen != 0U ||
        memcmp(frame + AGENTBOX_WBR_OFFSET_MAGIC, AGENTBOX_WBR_MAGIC, 4U) != 0 ||
        frame[AGENTBOX_WBR_OFFSET_VERSION] != AGENTBOX_WBR_VERSION ||
        frame[AGENTBOX_WBR_OFFSET_MESSAGE_TYPE] != AGENTBOX_WBR_MESSAGE_RESIZE ||
        frame[AGENTBOX_WBR_OFFSET_FLAGS] != 0U || frame[AGENTBOX_WBR_OFFSET_FLAGS + 1U] != 0U ||
        frame[AGENTBOX_WBR_OFFSET_REQUEST_OR_ACK] != AGENTBOX_WBR_RESIZE_MARKER) {
        errno = EPROTO;
        return -1;
    }
    for (index = AGENTBOX_WBR_OFFSET_RESERVED; index < sizeof(frame); ++index) {
        if (frame[index] != 0U) {
            errno = EPROTO;
            return -1;
        }
    }
    sequence = from_network_u64(frame + AGENTBOX_WBR_OFFSET_SEQUENCE);
    supplied_generation = from_network_u64(frame + AGENTBOX_WBR_OFFSET_GENERATION);
    memcpy(&columns, frame + AGENTBOX_WBR_OFFSET_COLUMNS, sizeof(columns));
    memcpy(&rows, frame + AGENTBOX_WBR_OFFSET_ROWS, sizeof(rows));
    columns = ntohs(columns);
    rows = ntohs(rows);
    if (sequence == 0U || sequence <= *last_sequence || supplied_generation != generation ||
        columns < AGENTBOX_WBR_MIN_COLUMNS || columns > AGENTBOX_WBR_MAX_COLUMNS ||
        rows < AGENTBOX_WBR_MIN_ROWS || rows > AGENTBOX_WBR_MAX_ROWS) {
        errno = EPROTO;
        return -1;
    }
    memset(&geometry, 0, sizeof(geometry));
    geometry.ws_col = columns;
    geometry.ws_row = rows;
    if (ioctl(master, TIOCSWINSZ, &geometry) != 0) {
        return -1;
    }
    frame[AGENTBOX_WBR_OFFSET_MESSAGE_TYPE] = AGENTBOX_WBR_MESSAGE_ACK;
    frame[AGENTBOX_WBR_OFFSET_REQUEST_OR_ACK] = AGENTBOX_WBR_ACK_MARKER;
    to_network_u64(frame + AGENTBOX_WBR_OFFSET_SEQUENCE, sequence);
    to_network_u64(frame + AGENTBOX_WBR_OFFSET_GENERATION, generation);
    if (send(wbr, frame, sizeof(frame), MSG_DONTWAIT | MSG_NOSIGNAL) != (ssize_t)sizeof(frame)) {
        return -1;
    }
    *last_sequence = sequence;
    return 0;
}

static int relay_until_exit(int master, int wbr, int pid, int pidfd,
                            const struct agentbox_waw_bridge_config *config) {
    struct relay_buffer to_vendor;
    struct relay_buffer from_vendor;
    int input_eof = 0;
    int terminal_eof = 0;
    int child_status = 0;
    int child_exited = 0;
    int descendants_reaped = 0;
    struct timespec drain_deadline;
    uint64_t last_sequence = 0;
    memset(&to_vendor, 0, sizeof(to_vendor));
    memset(&from_vendor, 0, sizeof(from_vendor));
    if (set_nonblocking(STDIN_FILENO) != 0 || set_nonblocking(STDOUT_FILENO) != 0 ||
        set_nonblocking(master) != 0 || set_nonblocking(wbr) != 0) {
        return -1;
    }
    memset(&drain_deadline, 0, sizeof(drain_deadline));
    while (child_exited == 0 || terminal_eof == 0 || from_vendor.begin != from_vendor.end) {
        struct pollfd watched[6];
        nfds_t count = 0;
        int result;
        if (stop_requested != 0) {
            return -1;
        }
        if (child_exited != 0 && descendants_reaped != 0 && terminal_eof == 0) {
            struct timespec now;
            if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
                return -1;
            }
            if (now.tv_sec > drain_deadline.tv_sec ||
                (now.tv_sec == drain_deadline.tv_sec && now.tv_nsec >= drain_deadline.tv_nsec)) {
                errno = ETIMEDOUT;
                return -1;
            }
        }
        if (input_eof == 0 && to_vendor.end < sizeof(to_vendor.bytes)) {
            watched[count].fd = STDIN_FILENO;
            watched[count].events = POLLIN;
            watched[count].revents = 0;
            ++count;
        }
        if (to_vendor.begin != to_vendor.end) {
            watched[count].fd = master;
            watched[count].events = POLLOUT;
            watched[count].revents = 0;
            ++count;
        }
        if (terminal_eof == 0 && from_vendor.end < sizeof(from_vendor.bytes)) {
            watched[count].fd = master;
            watched[count].events = POLLIN;
            watched[count].revents = 0;
            ++count;
        }
        if (from_vendor.begin != from_vendor.end) {
            watched[count].fd = STDOUT_FILENO;
            watched[count].events = POLLOUT;
            watched[count].revents = 0;
            ++count;
        }
        watched[count].fd = wbr;
        watched[count].events = POLLIN;
        watched[count].revents = 0;
        ++count;
        if (child_exited == 0) {
            watched[count].fd = pidfd;
            watched[count].events = POLLIN;
            watched[count].revents = 0;
            ++count;
        }
        if (child_exited != 0 && descendants_reaped == 0) {
            if (reap_namespace_descendants() != 0) {
                return -1;
            }
            descendants_reaped = 1;
            input_eof = 1;
            to_vendor.begin = 0U;
            to_vendor.end = 0U;
            if (clock_gettime(CLOCK_MONOTONIC, &drain_deadline) != 0) {
                return -1;
            }
            drain_deadline.tv_sec += 1;
        }
        result = poll(watched, count, 100);
        if (result < 0) {
            if (errno == EINTR) {
                continue;
            }
            return -1;
        }
        {
            nfds_t index;
            for (index = 0; index < count; ++index) {
                const short events = watched[index].revents;
                if ((events & POLLNVAL) != 0) {
                    return -1;
                }
                if (watched[index].fd == STDIN_FILENO && (events & (POLLIN | POLLHUP)) != 0 &&
                    buffer_read(STDIN_FILENO, &to_vendor, &input_eof) != 0) {
                    return -1;
                }
                if (watched[index].fd == master && (events & POLLOUT) != 0 &&
                    to_vendor.begin != to_vendor.end && buffer_write(master, &to_vendor) != 0) {
                    return -1;
                }
                if (watched[index].fd == master &&
                    (events & (POLLIN | POLLHUP | POLLERR)) != 0 &&
                    terminal_eof == 0 && buffer_read(master, &from_vendor, &terminal_eof) != 0) {
                    return -1;
                }
                if (watched[index].fd == STDOUT_FILENO && (events & POLLOUT) != 0 &&
                    from_vendor.begin != from_vendor.end &&
                    buffer_write(STDOUT_FILENO, &from_vendor) != 0) {
                    return -1;
                }
                if (watched[index].fd == STDOUT_FILENO &&
                    (events & (POLLHUP | POLLERR)) != 0) {
                    return -1;
                }
                if (watched[index].fd == wbr && (events & (POLLIN | POLLHUP | POLLERR)) != 0 &&
                    handle_resize(master, wbr, config->generation, &last_sequence) != 0) {
                    return -1;
                }
                if (watched[index].fd == pidfd && (events & (POLLIN | POLLHUP | POLLERR)) != 0) {
                    pid_t waited = waitpid((pid_t)pid, &child_status, WNOHANG);
                    if (waited == (pid_t)pid) {
                        child_exited = 1;
                    } else if (waited < 0 && errno != EINTR) {
                        return -1;
                    }
                }
            }
        }
        if (child_exited == 0) {
            pid_t waited = waitpid((pid_t)pid, &child_status, WNOHANG);
            if (waited == (pid_t)pid) {
                child_exited = 1;
            } else if (waited < 0 && errno != EINTR) {
                return -1;
            }
        }
        if (child_exited != 0 && terminal_eof != 0 && from_vendor.begin == from_vendor.end) {
            break;
        }
    }
    (void)close(pidfd);
    if (WIFEXITED(child_status)) {
        return WEXITSTATUS(child_status);
    }
    if (WIFSIGNALED(child_status)) {
        return 128 + WTERMSIG(child_status);
    }
    return 125;
}

static int run_bridge(void) {
    struct agentbox_waw_bridge_config config;
    unsigned char trailing;
    int master = -1;
    int slave = -1;
    int exec_status[2] = {-1, -1};
    pid_t child;
    int pidfd;
    if (agentbox_waw_read_exact(AGENTBOX_WAW_BRIDGE_CONFIG_FD, &config, sizeof(config)) != 0 ||
        read(AGENTBOX_WAW_BRIDGE_CONFIG_FD, &trailing, 1U) != 0 || validate_config(&config) != 0 ||
        validate_bridge_descriptors() != 0 || agentbox_waw_apply_basic_limits() != 0 ||
        agentbox_waw_apply_no_new_privs() != 0 || prctl(PR_SET_CHILD_SUBREAPER, 1UL) != 0 ||
        open_terminal(&config, &master, &slave) != 0 || pipe2(exec_status, O_CLOEXEC) != 0) {
        return 65;
    }
    child = fork();
    if (child < 0) {
        (void)close(master);
        (void)close(slave);
        (void)close(exec_status[0]);
        (void)close(exec_status[1]);
        return 71;
    }
    if (child == 0) {
        (void)close(exec_status[0]);
        vendor_child(&config, master, slave, exec_status[1]);
    }
    (void)close(slave);
    (void)close(exec_status[1]);
    pidfd = agentbox_waw_pidfd_open((int)child);
    if (pidfd < 0) {
        agentbox_waw_terminate_and_reap((int)child, -1);
        (void)close(master);
        (void)close(exec_status[0]);
        return 71;
    }
    if (install_signal_handlers() != 0 ||
        agentbox_waw_confirm_exec(exec_status[0], pidfd) != 0 || close(exec_status[0]) != 0 ||
        agentbox_waw_send_ready(AGENTBOX_WAW_BRIDGE_READY_FD) != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        (void)close(master);
        return 71;
    }
    (void)close(AGENTBOX_WAW_BRIDGE_READY_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_CONFIG_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_PROJECT_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_HOME_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_TEMP_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD);
    (void)close(AGENTBOX_WAW_BRIDGE_POLICY_FD);
    {
        int result = relay_until_exit(master, AGENTBOX_WAW_BRIDGE_WBR_FD, (int)child, pidfd,
                                      &config);
        if (result < 0) {
            agentbox_waw_terminate_and_reap((int)child, pidfd);
            (void)reap_namespace_descendants();
            result = 74;
        }
        (void)close(master);
        (void)close(AGENTBOX_WAW_BRIDGE_WBR_FD);
        return result;
    }
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-bridge " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    if (argc != 1) {
        return 64;
    }
    return run_bridge();
}

#else

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-bridge " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    (void)argv;
    return 78;
}

#endif
