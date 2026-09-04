#define _GNU_SOURCE

#include "waw_native.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)

#include <sys/prctl.h>

static volatile sig_atomic_t child_to_stop = 0;

static void remember_signal(int signal_number) {
    (void)signal_number;
    if (child_to_stop > 0) {
        (void)kill((pid_t)child_to_stop, SIGTERM);
    }
}

static int install_signal_handlers(void) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = remember_signal;
    (void)sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) != 0 || sigaction(SIGINT, &action, NULL) != 0 ||
        sigaction(SIGHUP, &action, NULL) != 0) {
        return -1;
    }
    action.sa_handler = SIG_IGN;
    return sigaction(SIGPIPE, &action, NULL);
}

static int validate_attach_descriptors(void) {
    return agentbox_waw_validate_executable_fd(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD) == 0 &&
                   agentbox_waw_validate_directory_fd(AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD) ==
                       0 &&
                   agentbox_waw_validate_regular_fd(AGENTBOX_WAW_ATTACH_CONFIG_FD) == 0 &&
                   agentbox_waw_validate_seqpacket_fd(AGENTBOX_WAW_ATTACH_READY_FD) == 0
               ? 0
               : -1;
}

static void attach_failure(int status_fd) {
    const unsigned char failed = 1U;
    (void)agentbox_waw_write_exact(status_fd, &failed, sizeof(failed));
    _exit(125);
}

static void attach_child(const char *workspace_hash, enum agentbox_waw_agent_type agent,
                         int status_fd) {
    char socket_path[96];
    char target[80];
    char config_path[32];
    char *arguments[9];
    char *environment[] = {(char *)"HOME=/nonexistent", (char *)"PATH=/usr/bin",
                           (char *)"LANG=C.UTF-8", (char *)"LC_CTYPE=C.UTF-8",
                           (char *)"TERM=xterm-256color", NULL};
    int kept[4] = {AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD,
                   AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD,
                   AGENTBOX_WAW_ATTACH_CONFIG_FD, status_fd};
    const char *agent_name = agentbox_waw_agent_name(agent);
    pid_t expected_parent = getppid();
    int socket_length;
    int target_length;
    int config_length;
    if (expected_parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent || agent_name == NULL) {
        attach_failure(status_fd);
    }
    socket_length = snprintf(socket_path, sizeof(socket_path), "/proc/self/fd/%d/%.32s.sock",
                             AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD, workspace_hash);
    target_length = snprintf(target, sizeof(target), "=agentbox-waw-%s-%.32s", agent_name,
                             workspace_hash);
    config_length = snprintf(config_path, sizeof(config_path), "/proc/self/fd/%d",
                             AGENTBOX_WAW_ATTACH_CONFIG_FD);
    if (socket_length < 0 || (size_t)socket_length >= sizeof(socket_path) || target_length < 0 ||
        (size_t)target_length >= sizeof(target) || config_length < 0 ||
        (size_t)config_length >= sizeof(config_path) ||
        agentbox_waw_apply_basic_limits() != 0 || agentbox_waw_apply_no_new_privs() != 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD, 1) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0) {
        attach_failure(status_fd);
    }
    arguments[0] = (char *)"tmux";
    arguments[1] = (char *)"-S";
    arguments[2] = socket_path;
    arguments[3] = (char *)"-f";
    arguments[4] = config_path;
    arguments[5] = (char *)"attach-session";
    arguments[6] = (char *)"-t";
    arguments[7] = target;
    arguments[8] = NULL;
    (void)agentbox_waw_exec_held(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD, arguments, environment);
    attach_failure(status_fd);
}

static void query_child(const char *workspace_hash, enum agentbox_waw_agent_type agent,
                        int output_fd) {
    char socket_path[96];
    char target[80];
    char *arguments[9];
    char *environment[] = {(char *)"HOME=/nonexistent", (char *)"PATH=/usr/bin",
                           (char *)"LANG=C.UTF-8", (char *)"LC_CTYPE=C.UTF-8", NULL};
    int kept[2] = {AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD,
                   AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD};
    const char *agent_name = agentbox_waw_agent_name(agent);
    pid_t expected_parent = getppid();
    int socket_length;
    int target_length;
    if (agent_name == NULL || expected_parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent || dup2(output_fd, STDOUT_FILENO) < 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD, 1) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0) {
        _exit(125);
    }
    socket_length = snprintf(socket_path, sizeof(socket_path), "/proc/self/fd/%d/%.32s.sock",
                             AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD, workspace_hash);
    target_length = snprintf(target, sizeof(target), "=agentbox-waw-%s-%.32s", agent_name,
                             workspace_hash);
    if (socket_length < 0 || (size_t)socket_length >= sizeof(socket_path) || target_length < 0 ||
        (size_t)target_length >= sizeof(target)) {
        _exit(125);
    }
    arguments[0] = (char *)"tmux";
    arguments[1] = (char *)"-S";
    arguments[2] = socket_path;
    arguments[3] = (char *)"list-clients";
    arguments[4] = (char *)"-t";
    arguments[5] = target;
    arguments[6] = (char *)"-F";
    arguments[7] = (char *)"#{client_pid}:#{session_name}";
    arguments[8] = NULL;
    (void)agentbox_waw_exec_held(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD, arguments, environment);
    _exit(126);
}

static int query_attached_client_once(const char *workspace_hash,
                                      enum agentbox_waw_agent_type agent, pid_t attach_pid) {
    int output[2];
    pid_t query;
    int query_pidfd;
    struct pollfd watched[2];
    char observed[256];
    char expected[160];
    ssize_t size;
    int status;
    int expected_length;
    const char *agent_name = agentbox_waw_agent_name(agent);
    if (agent_name == NULL || pipe2(output, O_CLOEXEC) != 0) {
        return -1;
    }
    query = fork();
    if (query < 0) {
        (void)close(output[0]);
        (void)close(output[1]);
        return -1;
    }
    if (query == 0) {
        (void)close(output[0]);
        query_child(workspace_hash, agent, output[1]);
    }
    (void)close(output[1]);
    query_pidfd = agentbox_waw_pidfd_open((int)query);
    if (query_pidfd < 0) {
        agentbox_waw_terminate_and_reap((int)query, -1);
        (void)close(output[0]);
        return -1;
    }
    watched[0].fd = output[0];
    watched[0].events = POLLIN | POLLHUP;
    watched[0].revents = 0;
    watched[1].fd = query_pidfd;
    watched[1].events = POLLIN;
    watched[1].revents = 0;
    if (poll(watched, 2U, 120) <= 0) {
        agentbox_waw_terminate_and_reap((int)query, query_pidfd);
        (void)close(output[0]);
        return 0;
    }
    size = read(output[0], observed, sizeof(observed) - 1U);
    (void)close(output[0]);
    watched[1].revents = 0;
    if (poll(&watched[1], 1U, 30) <= 0) {
        agentbox_waw_terminate_and_reap((int)query, query_pidfd);
        return 0;
    }
    (void)close(query_pidfd);
    while (waitpid(query, &status, 0) < 0) {
        if (errno != EINTR) {
            return -1;
        }
    }
    if (size < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        return 0;
    }
    observed[(size_t)size] = '\0';
    expected_length = snprintf(expected, sizeof(expected), "%ld:agentbox-waw-%s-%.32s\n",
                               (long)attach_pid, agent_name, workspace_hash);
    return expected_length > 0 && (size_t)expected_length < sizeof(expected) &&
                   strcmp(observed, expected) == 0
               ? 1
               : 0;
}

static int confirm_attached_client(const char *workspace_hash, enum agentbox_waw_agent_type agent,
                                   pid_t attach_pid, int attach_pidfd) {
    struct pollfd alive;
    struct timespec pause = {0, 20000000L};
    int attempt;
    alive.fd = attach_pidfd;
    alive.events = POLLIN;
    for (attempt = 0; attempt < 4; ++attempt) {
        int result;
        alive.revents = 0;
        if (poll(&alive, 1U, 0) != 0) {
            return -1;
        }
        result = query_attached_client_once(workspace_hash, agent, attach_pid);
        if (result == 1) {
            alive.revents = 0;
            return poll(&alive, 1U, 0) == 0 ? 0 : -1;
        }
        if (result < 0) {
            return -1;
        }
        (void)nanosleep(&pause, NULL);
    }
    errno = ETIMEDOUT;
    return -1;
}

static int run_attach(const char *workspace_hash, enum agentbox_waw_agent_type agent) {
    pid_t child;
    int pidfd;
    int exec_status[2] = {-1, -1};
    pid_t expected_parent = getppid();
    int kept[4] = {AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD,
                   AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD,
                   AGENTBOX_WAW_ATTACH_CONFIG_FD,
                   AGENTBOX_WAW_ATTACH_READY_FD};
    if (expected_parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent ||
        validate_attach_descriptors() != 0 || !isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) ||
        !isatty(STDERR_FILENO) ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0 ||
        agentbox_waw_apply_basic_limits() != 0 || agentbox_waw_apply_no_new_privs() != 0) {
        return 65;
    }
    if (getsid(0) != getpid() && setsid() < 0) {
        return 72;
    }
    if (ioctl(STDIN_FILENO, TIOCSCTTY, 0) != 0 && errno != EPERM) {
        return 73;
    }
    if (pipe2(exec_status, O_CLOEXEC) != 0) {
        return 74;
    }
    child = fork();
    if (child < 0) {
        (void)close(exec_status[0]);
        (void)close(exec_status[1]);
        return 75;
    }
    if (child == 0) {
        (void)close(exec_status[0]);
        attach_child(workspace_hash, agent, exec_status[1]);
    }
    (void)close(exec_status[1]);
    child_to_stop = (sig_atomic_t)child;
    pidfd = agentbox_waw_pidfd_open((int)child);
    if (pidfd < 0) {
        agentbox_waw_terminate_and_reap((int)child, -1);
        (void)close(exec_status[0]);
        return 76;
    }
    if (install_signal_handlers() != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        return 77;
    }
    if (agentbox_waw_confirm_exec_timeout(exec_status[0], pidfd, 200) != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        return 78;
    }
    if (close(exec_status[0]) != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        return 79;
    }
    if (confirm_attached_client(workspace_hash, agent, child, pidfd) != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        return 80;
    }
    if (agentbox_waw_send_ready(AGENTBOX_WAW_ATTACH_READY_FD) != 0) {
        agentbox_waw_terminate_and_reap((int)child, pidfd);
        return 81;
    }
    (void)close(AGENTBOX_WAW_ATTACH_TMUX_EXECUTABLE_FD);
    (void)close(AGENTBOX_WAW_ATTACH_SOCKET_DIRECTORY_FD);
    (void)close(AGENTBOX_WAW_ATTACH_CONFIG_FD);
    (void)close(AGENTBOX_WAW_ATTACH_READY_FD);
    {
        int result = agentbox_waw_wait_child((int)child, pidfd);
        child_to_stop = 0;
        (void)close(pidfd);
        return result;
    }
}

int main(int argc, char **argv) {
    enum agentbox_waw_agent_type agent;
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-attach-supervisor " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    if (argc != 5 || strcmp(argv[1], "--workspace-hash") != 0 ||
        !agentbox_waw_is_hex_digest(argv[2]) || strcmp(argv[3], "--agent-type") != 0 ||
        agentbox_waw_parse_agent(argv[4], &agent) != 0) {
        return 64;
    }
    return run_attach(argv[2], agent);
}

#else

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-attach-supervisor " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    (void)argv;
    return 78;
}

#endif
