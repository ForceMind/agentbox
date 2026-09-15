#define _GNU_SOURCE

#include "waw_native.h"
#include "waw_isolation.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>

#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)

#include <sys/prctl.h>

_Static_assert(AGENTBOX_WAW_AUTH_OFFSET_RESERVED + AGENTBOX_WAW_AUTH_RESERVED_BYTES ==
                   AGENTBOX_WAW_AUTH_RECORD_BYTES,
               "auth record layout");
_Static_assert(AGENTBOX_WAW_AUTH_READY_FRAME_BYTES == 8U, "auth ready layout");

struct launch_values {
    enum agentbox_waw_agent_type agent;
    uint64_t generation;
    uint32_t runtime_uid;
    uint32_t runtime_gid;
    uint16_t columns;
    uint16_t rows;
    char workspace_hash[65];
    char profile_digest[65];
};

static uint32_t auth_network_u32(const unsigned char *value) {
    return ((uint32_t)value[0] << 24U) | ((uint32_t)value[1] << 16U) |
           ((uint32_t)value[2] << 8U) | (uint32_t)value[3];
}

static uint64_t auth_network_u64(const unsigned char *value) {
    return ((uint64_t)auth_network_u32(value) << 32U) |
           (uint64_t)auth_network_u32(value + 4U);
}

static void close_ancillary_fds(struct msghdr *message) {
    struct cmsghdr *header;
    for (header = CMSG_FIRSTHDR(message); header != NULL;
         header = CMSG_NXTHDR(message, header)) {
        if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS &&
            header->cmsg_len >= CMSG_LEN(0U)) {
            const size_t payload = header->cmsg_len - CMSG_LEN(0U);
            const size_t count = payload / sizeof(int);
            const int *descriptors = (const int *)CMSG_DATA(header);
            size_t index;
            for (index = 0; index < count; ++index) {
                (void)close(descriptors[index]);
            }
        }
    }
}

static int validate_auth_peer(uint32_t runtime_pid, uint32_t runtime_uid,
                              uint32_t runtime_gid) {
#if defined(SO_PEERCRED)
    struct ucred credentials;
    socklen_t length = (socklen_t)sizeof(credentials);
    if (getsockopt(AGENTBOX_WAW_AUTH_CONTROL_FD, SOL_SOCKET, SO_PEERCRED, &credentials,
                   &length) != 0 ||
        length != (socklen_t)sizeof(credentials) || credentials.pid != (pid_t)runtime_pid ||
        credentials.uid != (uid_t)runtime_uid || credentials.gid != (gid_t)runtime_gid) {
        errno = EACCES;
        return -1;
    }
    return 0;
#else
    (void)runtime_pid;
    (void)runtime_uid;
    (void)runtime_gid;
    errno = ENOTSUP;
    return -1;
#endif
}

static int receive_auth_record(unsigned char raw[AGENTBOX_WAW_AUTH_RECORD_BYTES]) {
    unsigned char packet[AGENTBOX_WAW_AUTH_RECORD_BYTES + 1U];
    unsigned char extra = 0U;
    unsigned char control[CMSG_SPACE(sizeof(int) * 16U)];
    struct iovec vector;
    struct msghdr message;
    ssize_t received;
    memset(&message, 0, sizeof(message));
    memset(control, 0, sizeof(control));
    vector.iov_base = packet;
    vector.iov_len = sizeof(packet);
    message.msg_iov = &vector;
    message.msg_iovlen = 1U;
    message.msg_control = control;
    message.msg_controllen = sizeof(control);
    received = recvmsg(AGENTBOX_WAW_AUTH_CONTROL_FD, &message, MSG_CMSG_CLOEXEC);
    if (message.msg_controllen != 0U) {
        close_ancillary_fds(&message);
    }
    if (received != (ssize_t)AGENTBOX_WAW_AUTH_RECORD_BYTES ||
        (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0 ||
        message.msg_controllen != 0U) {
        errno = EPROTO;
        return -1;
    }
    memcpy(raw, packet, (size_t)AGENTBOX_WAW_AUTH_RECORD_BYTES);

    memset(&message, 0, sizeof(message));
    memset(control, 0, sizeof(control));
    vector.iov_base = &extra;
    vector.iov_len = sizeof(extra);
    message.msg_iov = &vector;
    message.msg_iovlen = 1U;
    message.msg_control = control;
    message.msg_controllen = sizeof(control);
    received = recvmsg(AGENTBOX_WAW_AUTH_CONTROL_FD, &message, MSG_CMSG_CLOEXEC);
    if (message.msg_controllen != 0U) {
        close_ancillary_fds(&message);
    }
    if (received != 0 || (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0 ||
        message.msg_controllen != 0U) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int parse_auth_record(const unsigned char raw[AGENTBOX_WAW_AUTH_RECORD_BYTES],
                             struct agentbox_waw_auth_probe_config *config,
                             uint32_t *runtime_pid) {
    size_t index;
    if (memcmp(raw + AGENTBOX_WAW_AUTH_OFFSET_MAGIC, AGENTBOX_WAW_AUTH_RECORD_MAGIC, 4U) != 0 ||
        raw[AGENTBOX_WAW_AUTH_OFFSET_VERSION] != AGENTBOX_WAW_AUTH_RECORD_VERSION ||
        (raw[AGENTBOX_WAW_AUTH_OFFSET_AGENT_TYPE] !=
             (unsigned char)AGENTBOX_WAW_AGENT_CLAUDE &&
         raw[AGENTBOX_WAW_AUTH_OFFSET_AGENT_TYPE] !=
             (unsigned char)AGENTBOX_WAW_AGENT_CODEX) ||
        raw[AGENTBOX_WAW_AUTH_OFFSET_FLAGS] != 0U ||
        raw[AGENTBOX_WAW_AUTH_OFFSET_FLAGS + 1U] != 0U) {
        errno = EPROTO;
        return -1;
    }
    for (index = 0; index < (size_t)AGENTBOX_WAW_AUTH_RESERVED_BYTES; ++index) {
        if (raw[AGENTBOX_WAW_AUTH_OFFSET_RESERVED + index] != 0U) {
            errno = EPROTO;
            return -1;
        }
    }
    memset(config, 0, sizeof(*config));
    config->agent_type = raw[AGENTBOX_WAW_AUTH_OFFSET_AGENT_TYPE];
    *runtime_pid = auth_network_u32(raw + AGENTBOX_WAW_AUTH_OFFSET_RUNTIME_PID);
    config->runtime_uid = auth_network_u32(raw + AGENTBOX_WAW_AUTH_OFFSET_RUNTIME_UID);
    config->runtime_gid = auth_network_u32(raw + AGENTBOX_WAW_AUTH_OFFSET_RUNTIME_GID);
    config->generation = auth_network_u64(raw + AGENTBOX_WAW_AUTH_OFFSET_GENERATION);
    memcpy(config->workspace_hash, raw + AGENTBOX_WAW_AUTH_OFFSET_WORKSPACE_HASH,
           (size_t)AGENTBOX_WAW_WORKSPACE_HASH_BYTES);
    memcpy(config->profile_digest, raw + AGENTBOX_WAW_AUTH_OFFSET_PROFILE_DIGEST,
           (size_t)AGENTBOX_WAW_PROFILE_DIGEST_BYTES);
    config->workspace_hash[AGENTBOX_WAW_WORKSPACE_HASH_BYTES] = '\0';
    config->profile_digest[AGENTBOX_WAW_PROFILE_DIGEST_BYTES] = '\0';
    if (*runtime_pid == 0U || config->runtime_uid == 0U || config->generation == 0U ||
        !agentbox_waw_is_hex_digest(config->workspace_hash) ||
        !agentbox_waw_is_hex_digest(config->profile_digest)) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int validate_auth_devnull(void) {
    struct stat supplied;
    struct stat expected;
    int flags = fcntl(AGENTBOX_WAW_AUTH_STDIN_FD, F_GETFL);
    return flags >= 0 && (flags & O_ACCMODE) == O_RDONLY &&
                   fstat(AGENTBOX_WAW_AUTH_STDIN_FD, &supplied) == 0 &&
                   stat("/dev/null", &expected) == 0 && S_ISCHR(supplied.st_mode) &&
                   supplied.st_dev == expected.st_dev && supplied.st_ino == expected.st_ino &&
                   supplied.st_rdev == expected.st_rdev
               ? 0
               : -1;
}

static int validate_auth_pipe(int fd, struct stat *status) {
    int flags = fcntl(fd, F_GETFL);
    return flags >= 0 && (flags & O_ACCMODE) == O_WRONLY && fstat(fd, status) == 0 &&
                   S_ISFIFO(status->st_mode)
               ? 0
               : -1;
}

static int validate_owned_directory(int fd, uid_t owner, int private_directory,
                                    struct stat *status) {
    if (agentbox_waw_validate_directory_fd(fd) != 0 || fstat(fd, status) != 0 ||
        status->st_uid != owner ||
        (private_directory != 0 && (status->st_mode & (S_IRWXG | S_IRWXO)) != 0) ||
        (status->st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int descriptor_matches_directory(int fd, const char *path) {
    struct stat supplied;
    struct stat expected;
    if (fstat(fd, &supplied) != 0 || lstat(path, &expected) != 0 ||
        !S_ISDIR(supplied.st_mode) || !S_ISDIR(expected.st_mode) ||
        supplied.st_dev != expected.st_dev || supplied.st_ino != expected.st_ino ||
        supplied.st_mode != expected.st_mode || supplied.st_uid != expected.st_uid ||
        supplied.st_gid != expected.st_gid) {
        errno = EXDEV;
        return -1;
    }
    return 0;
}

static int validate_auth_roles(const struct agentbox_waw_auth_probe_config *config) {
    struct stat output;
    struct stat error;
    struct stat cgroup;
    struct stat executable;
    struct stat home;
    struct stat scratch;
    struct stat policy;
    char scratch_path[192];
    const char *home_path = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE
                                ? "/var/lib/agentbox-waw/vendor-homes/claude"
                                : "/var/lib/agentbox-waw/vendor-homes/codex";
    const char *policy_path = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE
                                  ? "/etc/claude-code"
                                  : "/etc/codex";
    int scratch_length = snprintf(scratch_path, sizeof(scratch_path),
                                  AGENTBOX_WAW_RUN_ROOT "/tmp/%s/auth-probe-g%llu",
                                  config->workspace_hash,
                                  (unsigned long long)config->generation);
    if (scratch_length < 0 || (size_t)scratch_length >= sizeof(scratch_path) ||
        validate_auth_devnull() != 0 ||
        validate_auth_pipe(AGENTBOX_WAW_AUTH_STDOUT_FD, &output) != 0 ||
        validate_auth_pipe(AGENTBOX_WAW_AUTH_STDERR_FD, &error) != 0 ||
        (output.st_dev == error.st_dev && output.st_ino == error.st_ino) ||
        agentbox_waw_validate_seqpacket_fd(AGENTBOX_WAW_AUTH_CONTROL_FD) != 0 ||
        agentbox_waw_validate_directory_fd(AGENTBOX_WAW_AUTH_CGROUP_FD) != 0 ||
        fstat(AGENTBOX_WAW_AUTH_CGROUP_FD, &cgroup) != 0 ||
        agentbox_waw_validate_executable_fd(AGENTBOX_WAW_AUTH_VENDOR_EXECUTABLE_FD) != 0 ||
        fstat(AGENTBOX_WAW_AUTH_VENDOR_EXECUTABLE_FD, &executable) != 0 ||
        validate_owned_directory(AGENTBOX_WAW_AUTH_HOME_FD, (uid_t)config->runtime_uid, 1,
                                 &home) != 0 ||
        descriptor_matches_directory(AGENTBOX_WAW_AUTH_HOME_FD, home_path) != 0 ||
        validate_owned_directory(AGENTBOX_WAW_AUTH_SCRATCH_FD, (uid_t)config->runtime_uid, 1,
                                 &scratch) != 0 ||
        descriptor_matches_directory(AGENTBOX_WAW_AUTH_SCRATCH_FD, scratch_path) != 0 ||
        validate_owned_directory(AGENTBOX_WAW_AUTH_POLICY_FD, 0U, 0, &policy) != 0 ||
        descriptor_matches_directory(AGENTBOX_WAW_AUTH_POLICY_FD, policy_path) != 0 ||
        (home.st_mode & 07777U) != 0700U || (scratch.st_mode & 07777U) != 0700U ||
        (policy.st_mode & 07777U) != 0755U ||
        (home.st_dev == scratch.st_dev && home.st_ino == scratch.st_ino) ||
        (home.st_dev == policy.st_dev && home.st_ino == policy.st_ino) ||
        (scratch.st_dev == policy.st_dev && scratch.st_ino == policy.st_ino) ||
        (cgroup.st_dev == home.st_dev && cgroup.st_ino == home.st_ino) ||
        (executable.st_dev == policy.st_dev && executable.st_ino == policy.st_ino)) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int parse_cli_positive(const char *raw, uint64_t maximum, uint64_t *result) {
    const char *cursor = raw;
    uint64_t value = 0U;
    if (raw == NULL || raw[0] < '1' || raw[0] > '9') {
        errno = EINVAL;
        return -1;
    }
    while (*cursor != '\0') {
        const uint64_t digit = (uint64_t)(unsigned int)(*cursor - '0');
        if (*cursor < '0' || *cursor > '9' || value > (maximum - digit) / UINT64_C(10)) {
            errno = EINVAL;
            return -1;
        }
        value = value * UINT64_C(10) + digit;
        ++cursor;
    }
    *result = value;
    return 0;
}

static int place_self_in_cgroup(int cgroup_fd) {
    char pid[32];
    char observed[4096];
    int descriptor;
    int length = snprintf(pid, sizeof(pid), "%ld\n", (long)getpid());
    ssize_t count;
    char *cursor;
    if (length <= 0 || (size_t)length >= sizeof(pid)) {
        return -1;
    }
    descriptor = openat(cgroup_fd, "cgroup.procs", O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0 || agentbox_waw_write_exact(descriptor, pid, (size_t)length) != 0 ||
        close(descriptor) != 0) {
        if (descriptor >= 0) {
            (void)close(descriptor);
        }
        return -1;
    }
    descriptor = openat(cgroup_fd, "cgroup.procs", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) {
        return -1;
    }
    count = read(descriptor, observed, sizeof(observed) - 1U);
    if (count <= 0 || close(descriptor) != 0) {
        (void)close(descriptor);
        return -1;
    }
    observed[(size_t)count] = '\0';
    cursor = observed;
    while (*cursor != '\0') {
        char *end = strchr(cursor, '\n');
        const size_t size = end == NULL ? strlen(cursor) : (size_t)(end - cursor + 1);
        if (size == (size_t)length && memcmp(cursor, pid, size) == 0) {
            return 0;
        }
        if (end == NULL) {
            break;
        }
        cursor = end + 1;
    }
    errno = EPROTO;
    return -1;
}

static int launch_tmux(const char *workspace_hash, enum agentbox_waw_agent_type agent,
                       int runtime_pid, int bootstrap_fd) {
    char socket_path[128];
    char session[96];
    char bootstrap_path[64];
    char config_path[32];
    char *arguments[17];
    char *environment[] = {(char *)"HOME=/nonexistent", (char *)"PATH=/usr/bin",
                           (char *)"LANG=C.UTF-8", (char *)"LC_CTYPE=C.UTF-8",
                           (char *)"TERM=xterm-256color", NULL};
    int kept[4] = {AGENTBOX_WAW_LAUNCHER_CGROUP_FD,
                   AGENTBOX_WAW_LAUNCHER_TMUX_EXECUTABLE_FD,
                   AGENTBOX_WAW_LAUNCHER_TMUX_CONFIG_FD,
                   AGENTBOX_WAW_LAUNCHER_READY_FD};
    const char *agent_name = agentbox_waw_agent_name(agent);
    int socket_length;
    int session_length;
    int bootstrap_length;
    int config_length;
    if (agent_name == NULL) {
        return 71;
    }
    socket_length = snprintf(socket_path, sizeof(socket_path),
                             AGENTBOX_WAW_RUN_ROOT "/tmux/%.32s.sock", workspace_hash);
    session_length = snprintf(session, sizeof(session), "agentbox-waw-%s-%.32s", agent_name,
                              workspace_hash);
    bootstrap_length = snprintf(bootstrap_path, sizeof(bootstrap_path), "/proc/%d/fd/%d",
                                runtime_pid, bootstrap_fd);
    config_length = snprintf(config_path, sizeof(config_path), "/proc/self/fd/%d",
                             AGENTBOX_WAW_LAUNCHER_TMUX_CONFIG_FD);
    if (runtime_pid != (int)getppid() ||
        agentbox_waw_validate_directory_fd(AGENTBOX_WAW_LAUNCHER_CGROUP_FD) != 0 ||
        agentbox_waw_validate_executable_fd(AGENTBOX_WAW_LAUNCHER_TMUX_EXECUTABLE_FD) != 0 ||
        agentbox_waw_validate_regular_fd(AGENTBOX_WAW_LAUNCHER_TMUX_CONFIG_FD) != 0 ||
        agentbox_waw_validate_seqpacket_fd(AGENTBOX_WAW_LAUNCHER_READY_FD) != 0 ||
        socket_length < 0 || (size_t)socket_length >= sizeof(socket_path) ||
        session_length < 0 || (size_t)session_length >= sizeof(session) ||
        bootstrap_length < 0 || (size_t)bootstrap_length >= sizeof(bootstrap_path) ||
        config_length < 0 || (size_t)config_length >= sizeof(config_path) ||
        place_self_in_cgroup(AGENTBOX_WAW_LAUNCHER_CGROUP_FD) != 0 ||
        agentbox_waw_send_ready(AGENTBOX_WAW_LAUNCHER_READY_FD) != 0 ||
        close(AGENTBOX_WAW_LAUNCHER_READY_FD) != 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_LAUNCHER_CGROUP_FD, 1) != 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_LAUNCHER_TMUX_EXECUTABLE_FD, 1) != 0 ||
        agentbox_waw_set_cloexec(AGENTBOX_WAW_LAUNCHER_TMUX_CONFIG_FD, 0) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0 ||
        agentbox_waw_apply_basic_limits() != 0) {
        return 71;
    }
    arguments[0] = (char *)"tmux";
    arguments[1] = (char *)"-S";
    arguments[2] = socket_path;
    arguments[3] = (char *)"-f";
    arguments[4] = config_path;
    arguments[5] = (char *)"new-session";
    arguments[6] = (char *)"-d";
    arguments[7] = (char *)"-s";
    arguments[8] = session;
    arguments[9] = bootstrap_path;
    arguments[10] = (char *)"--workspace-hash";
    arguments[11] = (char *)workspace_hash;
    arguments[12] = (char *)"--agent-type";
    arguments[13] = (char *)agent_name;
    arguments[14] = NULL;
    (void)agentbox_waw_exec_held(AGENTBOX_WAW_LAUNCHER_TMUX_EXECUTABLE_FD, arguments,
                                 environment);
    return 71;
}

static int expect_literal(const char **cursor, const char *literal) {
    const size_t size = strlen(literal);
    if (strncmp(*cursor, literal, size) != 0) {
        errno = EPROTO;
        return -1;
    }
    *cursor += size;
    return 0;
}

static int validate_tmux_evidence(const char *workspace_hash) {
    const char *tmux = getenv("TMUX");
    const char *pane = getenv("TMUX_PANE");
    size_t index;
    size_t tmux_length;
    char expected[128];
    struct stat status;
    struct stat parent_executable;
    struct stat fixed_tmux;
    struct stat terminals[3];
    pid_t parent = getppid();
    char parent_path[64];
    char line[512];
    unsigned long long socket_inode = 0;
    FILE *unix_sockets;
    int descriptor;
    int expected_length = snprintf(expected, sizeof(expected), AGENTBOX_WAW_RUN_ROOT "/tmux/%.32s.sock",
                                   workspace_hash);
    if (tmux == NULL || pane == NULL || parent <= 1) {
        errno = EPROTO;
        return -1;
    }
    tmux_length = strnlen(tmux, 4097U);
    if (expected_length < 0 || (size_t)expected_length >= sizeof(expected) ||
        tmux_length <= (size_t)expected_length || tmux_length > 4096U ||
        strncmp(tmux, expected, (size_t)expected_length) != 0 ||
        tmux[expected_length] != ',' || lstat(expected, &status) != 0 ||
        !S_ISSOCK(status.st_mode) || pane[0] != '%' || pane[1] < '0' ||
        pane[1] > '9') {
        errno = EPROTO;
        return -1;
    }
    if (pane[1] == '0' && pane[2] != '\0') {
        errno = EPROTO;
        return -1;
    }
    for (index = 0; index < tmux_length; ++index) {
        const unsigned char current = (unsigned char)tmux[index];
        if (current < 0x20U || current == 0x7fU) {
            errno = EPROTO;
            return -1;
        }
    }
    for (index = 1U; pane[index] != '\0'; ++index) {
        if (index > 20U || pane[index] < '0' || pane[index] > '9') {
            errno = EPROTO;
            return -1;
        }
    }
    expected_length = snprintf(parent_path, sizeof(parent_path), "/proc/%ld/exe", (long)parent);
    if (expected_length < 0 || (size_t)expected_length >= sizeof(parent_path) ||
        stat(parent_path, &parent_executable) != 0 || stat("/usr/bin/tmux", &fixed_tmux) != 0 ||
        parent_executable.st_dev != fixed_tmux.st_dev ||
        parent_executable.st_ino != fixed_tmux.st_ino || !isatty(STDIN_FILENO) ||
        !isatty(STDOUT_FILENO) || !isatty(STDERR_FILENO) ||
        fstat(STDIN_FILENO, &terminals[0]) != 0 || fstat(STDOUT_FILENO, &terminals[1]) != 0 ||
        fstat(STDERR_FILENO, &terminals[2]) != 0 ||
        terminals[0].st_rdev != terminals[1].st_rdev ||
        terminals[0].st_rdev != terminals[2].st_rdev || tcgetpgrp(STDIN_FILENO) != getpgrp()) {
        errno = EPROTO;
        return -1;
    }
    unix_sockets = fopen("/proc/net/unix", "r");
    if (unix_sockets == NULL) {
        return -1;
    }
    while (fgets(line, sizeof(line), unix_sockets) != NULL) {
        unsigned long long inode;
        char path[128];
        if (sscanf(line, "%*s %*s %*s %*s %*s %*s %llu %127s", &inode, path) == 2 &&
            strcmp(path, expected) == 0) {
            socket_inode = inode;
            break;
        }
    }
    if (fclose(unix_sockets) != 0 || socket_inode == 0U) {
        errno = EPROTO;
        return -1;
    }
    for (descriptor = 0; descriptor < 256; ++descriptor) {
        char fd_path[64];
        char link[96];
        char socket_link[64];
        ssize_t link_size;
        expected_length = snprintf(fd_path, sizeof(fd_path), "/proc/%ld/fd/%d", (long)parent,
                                   descriptor);
        if (expected_length < 0 || (size_t)expected_length >= sizeof(fd_path)) {
            return -1;
        }
        link_size = readlink(fd_path, link, sizeof(link) - 1U);
        if (link_size <= 0 || (size_t)link_size >= sizeof(link)) {
            continue;
        }
        link[(size_t)link_size] = '\0';
        expected_length = snprintf(socket_link, sizeof(socket_link), "socket:[%llu]", socket_inode);
        if (expected_length > 0 && (size_t)expected_length < sizeof(socket_link) &&
            strcmp(link, socket_link) == 0) {
            return 0;
        }
    }
    errno = EPROTO;
    return -1;
}

static int validate_cgroup_marker(const char *workspace_hash, uint64_t generation) {
    char expected[128];
    char cgroup[1024];
    int fd;
    ssize_t size;
    int length = snprintf(expected, sizeof(expected), "/ws-%s-g%llu/workload",
                          workspace_hash, (unsigned long long)generation);
    if (length < 0 || (size_t)length >= sizeof(expected)) {
        return -1;
    }
    fd = open("/proc/self/cgroup", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        return -1;
    }
    size = read(fd, cgroup, sizeof(cgroup) - 1U);
    (void)close(fd);
    if (size <= 0 || (size_t)size >= sizeof(cgroup)) {
        return -1;
    }
    cgroup[(size_t)size] = '\0';
    {
        char *marker = strstr(cgroup, expected);
        if (strncmp(cgroup, "0::", 3U) != 0 || marker == NULL ||
            (marker[strlen(expected)] != '\n' && marker[strlen(expected)] != '\0')) {
            errno = EPROTO;
            return -1;
        }
    }
    return 0;
}

static int validate_auth_cgroup_marker(const char *workspace_hash, uint64_t generation) {
    char cgroup[1024];
    char path[1200];
    struct stat supplied;
    struct stat expected;
    int fd;
    ssize_t size;
    int length;
    if (validate_cgroup_marker(workspace_hash, generation) != 0) {
        return -1;
    }
    fd = open("/proc/self/cgroup", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        return -1;
    }
    size = read(fd, cgroup, sizeof(cgroup) - 1U);
    (void)close(fd);
    if (size <= 3 || (size_t)size >= sizeof(cgroup) || memcmp(cgroup, "0::", 3U) != 0) {
        errno = EPROTO;
        return -1;
    }
    cgroup[(size_t)size] = '\0';
    if (cgroup[(size_t)size - 1U] == '\n') {
        cgroup[(size_t)size - 1U] = '\0';
    }
    length = snprintf(path, sizeof(path), "/sys/fs/cgroup%s", cgroup + 3U);
    if (length < 0 || (size_t)length >= sizeof(path) || stat(path, &expected) != 0 ||
        fstat(AGENTBOX_WAW_AUTH_CGROUP_FD, &supplied) != 0 ||
        supplied.st_dev != expected.st_dev || supplied.st_ino != expected.st_ino ||
        supplied.st_mode != expected.st_mode || supplied.st_uid != expected.st_uid ||
        supplied.st_gid != expected.st_gid) {
        errno = EXDEV;
        return -1;
    }
    return 0;
}

static int establish_control(const char *workspace_hash) {
    struct sockaddr_un address;
    int fd;
    int length;
    fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (fd < 0) {
        return -1;
    }
    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    length = snprintf(address.sun_path, sizeof(address.sun_path),
                      AGENTBOX_WAW_RUN_ROOT "/tmp/%s/launch.v1.sock", workspace_hash);
    if (length < 0 || (size_t)length >= sizeof(address.sun_path) ||
        connect(fd, (struct sockaddr *)&address, sizeof(address)) != 0 ||
        (fd != AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD &&
         dup3(fd, AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD, 0) < 0)) {
        (void)close(fd);
        return -1;
    }
    if (fd != AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD) {
        (void)close(fd);
    }
    return agentbox_waw_set_cloexec(AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD, 0);
}

static int parse_ascii_token(const char **cursor, char *output, size_t output_size) {
    size_t length = 0;
    if (**cursor != '"') {
        errno = EPROTO;
        return -1;
    }
    *cursor += 1;
    while (**cursor != '\0' && **cursor != '"') {
        const unsigned char current = (unsigned char)**cursor;
        if (current < 0x21U || current > 0x7eU || current == (unsigned char)'\\' ||
            length + 1U >= output_size) {
            errno = EPROTO;
            return -1;
        }
        output[length] = (char)current;
        ++length;
        *cursor += 1;
    }
    if (**cursor != '"' || length == 0U) {
        errno = EPROTO;
        return -1;
    }
    output[length] = '\0';
    *cursor += 1;
    return 0;
}

static int parse_unsigned(const char **cursor, uint64_t maximum, uint64_t *output,
                          int quoted) {
    uint64_t value = 0;
    size_t digits = 0;
    if (quoted != 0 && **cursor != '"') {
        errno = EPROTO;
        return -1;
    }
    if (quoted != 0) {
        *cursor += 1;
    }
    if (**cursor < '0' || **cursor > '9') {
        errno = EPROTO;
        return -1;
    }
    if (**cursor == '0' && (*cursor)[1] >= '0' && (*cursor)[1] <= '9') {
        errno = EPROTO;
        return -1;
    }
    while (**cursor >= '0' && **cursor <= '9') {
        const uint64_t digit = (uint64_t)(unsigned int)(**cursor - '0');
        if (value > (maximum - digit) / UINT64_C(10)) {
            errno = ERANGE;
            return -1;
        }
        value = value * UINT64_C(10) + digit;
        ++digits;
        if (digits > 20U) {
            errno = ERANGE;
            return -1;
        }
        *cursor += 1;
    }
    if (quoted != 0) {
        if (**cursor != '"') {
            errno = EPROTO;
            return -1;
        }
        *cursor += 1;
    }
    *output = value;
    return 0;
}

static int parse_digest(const char **cursor, char output[65]) {
    if (parse_ascii_token(cursor, output, 65U) != 0 || !agentbox_waw_is_hex_digest(output)) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int parse_launch(const char *raw, struct launch_values *values) {
    const char *cursor = raw;
    char agent[16];
    uint64_t number = 0;
    if (expect_literal(&cursor, "{\"agent\":") != 0 ||
        parse_ascii_token(&cursor, agent, sizeof(agent)) != 0 ||
        agentbox_waw_parse_agent(agent, &values->agent) != 0 ||
        expect_literal(&cursor, ",\"fd_role_bitmap\":127,\"generation\":") != 0 ||
        parse_unsigned(&cursor, UINT64_MAX, &values->generation, 1) != 0 ||
        values->generation == 0U ||
        expect_literal(&cursor, ",\"initial_geometry\":{\"columns\":") != 0 ||
        parse_unsigned(&cursor, UINT16_MAX, &number, 0) != 0) {
        return -1;
    }
    values->columns = (uint16_t)number;
    if (values->columns < AGENTBOX_WBR_MIN_COLUMNS ||
        values->columns > AGENTBOX_WBR_MAX_COLUMNS ||
        expect_literal(&cursor, ",\"rows\":") != 0 ||
        parse_unsigned(&cursor, UINT16_MAX, &number, 0) != 0) {
        return -1;
    }
    values->rows = (uint16_t)number;
    if (values->rows < AGENTBOX_WBR_MIN_ROWS || values->rows > AGENTBOX_WBR_MAX_ROWS ||
        expect_literal(&cursor, "},\"profile_digest\":") != 0 ||
        parse_digest(&cursor, values->profile_digest) != 0 ||
        expect_literal(&cursor, ",\"runtime_gid\":") != 0 ||
        parse_unsigned(&cursor, UINT32_MAX - UINT64_C(1), &number, 0) != 0) {
        return -1;
    }
    values->runtime_gid = (uint32_t)number;
    if (expect_literal(&cursor, ",\"runtime_uid\":") != 0 ||
        parse_unsigned(&cursor, UINT32_MAX - UINT64_C(1), &number, 0) != 0) {
        return -1;
    }
    values->runtime_uid = (uint32_t)number;
    if (expect_literal(&cursor,
                       ",\"schema\":\"agentbox-waw-launch-v1\",\"type\":\"interactive\","
                       "\"workspace_hash\":") != 0 ||
        parse_digest(&cursor, values->workspace_hash) != 0 || expect_literal(&cursor, "}") != 0 ||
        *cursor != '\0') {
        return -1;
    }
    return 0;
}

static void close_received(int descriptors[AGENTBOX_WAW_FD_COUNT]) {
    size_t index;
    for (index = 0; index < (size_t)AGENTBOX_WAW_FD_COUNT; ++index) {
        if (descriptors[index] >= 0) {
            (void)close(descriptors[index]);
            descriptors[index] = -1;
        }
    }
}

static int receive_launch(char raw[AGENTBOX_WAW_LAUNCH_MAX_BYTES + 1U],
                          int descriptors[AGENTBOX_WAW_FD_COUNT]) {
    struct iovec vector;
    struct msghdr message;
    union {
        struct cmsghdr alignment;
        unsigned char bytes[CMSG_SPACE(sizeof(int) * AGENTBOX_WAW_FD_COUNT)];
    } control;
    struct cmsghdr *header;
    size_t control_count = 0;
    size_t rights_count = 0;
    int rights_shape_valid = 0;
    ssize_t received;
    size_t index;
    memset(&message, 0, sizeof(message));
    memset(&control, 0, sizeof(control));
    vector.iov_base = raw;
    vector.iov_len = (size_t)AGENTBOX_WAW_LAUNCH_MAX_BYTES + 1U;
    message.msg_iov = &vector;
    message.msg_iovlen = 1U;
    message.msg_control = control.bytes;
    message.msg_controllen = sizeof(control.bytes);
    received = recvmsg(AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD, &message, MSG_CMSG_CLOEXEC);
    for (header = CMSG_FIRSTHDR(&message); header != NULL;
         header = CMSG_NXTHDR(&message, header)) {
        ++control_count;
        if (header->cmsg_level == SOL_SOCKET && header->cmsg_type == SCM_RIGHTS &&
            header->cmsg_len >= CMSG_LEN(0U)) {
            const size_t payload_size = header->cmsg_len - CMSG_LEN(0U);
            if (payload_size % sizeof(int) == 0U) {
                const size_t available = payload_size / sizeof(int);
                const size_t room = (size_t)AGENTBOX_WAW_FD_COUNT - rights_count;
                const size_t copied = available < room ? available : room;
                const int *rights = (const int *)CMSG_DATA(header);
                size_t extra;
                memcpy(descriptors + rights_count, CMSG_DATA(header), copied * sizeof(int));
                rights_count += copied;
                for (extra = copied; extra < available; ++extra) {
                    (void)close(rights[extra]);
                }
                rights_shape_valid = available == (size_t)AGENTBOX_WAW_FD_COUNT ? 1 : 0;
            }
        }
    }
    if (received <= 0 || received > (ssize_t)AGENTBOX_WAW_LAUNCH_MAX_BYTES ||
        (message.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) != 0 || control_count != 1U ||
        rights_count != (size_t)AGENTBOX_WAW_FD_COUNT || rights_shape_valid == 0) {
        close_received(descriptors);
        errno = EPROTO;
        return -1;
    }
    raw[(size_t)received] = '\0';
    for (index = 0; index < (size_t)AGENTBOX_WAW_FD_COUNT; ++index) {
        size_t other;
        if (descriptors[index] < 0 || agentbox_waw_set_cloexec(descriptors[index], 1) != 0) {
            close_received(descriptors);
            return -1;
        }
        for (other = 0; other < index; ++other) {
            if (descriptors[index] == descriptors[other]) {
                close_received(descriptors);
                errno = EPROTO;
                return -1;
            }
        }
    }
    return 0;
}

static int validate_roles(const int descriptors[AGENTBOX_WAW_FD_COUNT]) {
    return agentbox_waw_validate_path_directory_fd(
               descriptors[AGENTBOX_WAW_FD_PROJECT_DIRECTORY]) == 0 &&
                   agentbox_waw_validate_directory_fd(
                       descriptors[AGENTBOX_WAW_FD_SELECTED_HOME_DIRECTORY]) == 0 &&
                   agentbox_waw_validate_directory_fd(descriptors[AGENTBOX_WAW_FD_TEMP_DIRECTORY]) ==
                       0 &&
                   agentbox_waw_validate_executable_fd(
                       descriptors[AGENTBOX_WAW_FD_BRIDGE_EXECUTABLE]) == 0 &&
                   agentbox_waw_validate_executable_fd(
                       descriptors[AGENTBOX_WAW_FD_VENDOR_EXECUTABLE]) == 0 &&
                   agentbox_waw_validate_directory_fd(descriptors[AGENTBOX_WAW_FD_POLICY_DIRECTORY]) ==
                       0 &&
                   agentbox_waw_validate_seqpacket_fd(descriptors[AGENTBOX_WAW_FD_WBR_ENDPOINT]) == 0
               ? 0
               : -1;
}

static int move_descriptor(int source, int destination) {
    if (source != destination && dup3(source, destination, 0) < 0) {
        return -1;
    }
    return agentbox_waw_set_cloexec(destination, 0);
}

static int run_bootstrap(const char *workspace_hash, enum agentbox_waw_agent_type agent) {
    char raw[AGENTBOX_WAW_LAUNCH_MAX_BYTES + 1U];
    int received[AGENTBOX_WAW_FD_COUNT] = {-1, -1, -1, -1, -1, -1, -1};
    int safe[AGENTBOX_WAW_FD_COUNT] = {-1, -1, -1, -1, -1, -1, -1};
    int config_pipe[2] = {-1, -1};
    struct launch_values launch;
    struct agentbox_waw_bridge_config config;
    int kept[9];
    size_t index;
    pid_t expected_parent = getppid();
    char *bridge_argv[] = {(char *)"agentbox-waw-bridge", NULL};
#if defined(AGENTBOX_WAW_SANITIZED)
    char *bridge_env[] = {(char *)"LANG=C.UTF-8", (char *)"LC_CTYPE=C.UTF-8",
                          (char *)"ASAN_OPTIONS=detect_leaks=0:abort_on_error=1", NULL};
#else
    char *bridge_env[] = {(char *)"LANG=C.UTF-8", (char *)"LC_CTYPE=C.UTF-8", NULL};
#endif
    memset(&launch, 0, sizeof(launch));
    if (expected_parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent || validate_tmux_evidence(workspace_hash) != 0 ||
        establish_control(workspace_hash) != 0 || receive_launch(raw, received) != 0 ||
        parse_launch(raw, &launch) != 0 || strcmp(workspace_hash, launch.workspace_hash) != 0 ||
        launch.agent != agent || launch.runtime_uid != (uint32_t)geteuid() ||
        launch.runtime_gid != (uint32_t)getegid() ||
        validate_cgroup_marker(workspace_hash, launch.generation) != 0 ||
        validate_roles(received) != 0) {
        close_received(received);
        return 65;
    }
    for (index = 0; index < (size_t)AGENTBOX_WAW_FD_COUNT; ++index) {
        safe[index] = agentbox_waw_duplicate_high(received[index]);
        if (safe[index] < 0) {
            close_received(received);
            close_received(safe);
            return 71;
        }
    }
    close_received(received);
    if (pipe2(config_pipe, O_CLOEXEC) != 0) {
        close_received(safe);
        return 71;
    }
    memset(&config, 0, sizeof(config));
    config.magic = AGENTBOX_WAW_BRIDGE_CONFIG_MAGIC;
    config.abi_version = AGENTBOX_WAW_NATIVE_ABI_VERSION;
    config.generation = launch.generation;
    config.runtime_uid = launch.runtime_uid;
    config.runtime_gid = launch.runtime_gid;
    config.columns = launch.columns;
    config.rows = launch.rows;
    config.agent_type = (uint8_t)launch.agent;
    (void)memcpy(config.workspace_hash, launch.workspace_hash, sizeof(config.workspace_hash));
    (void)memcpy(config.profile_digest, launch.profile_digest, sizeof(config.profile_digest));
    if (agentbox_waw_write_exact(config_pipe[1], &config, sizeof(config)) != 0 ||
        close(config_pipe[1]) != 0) {
        config_pipe[1] = -1;
        close_received(safe);
        (void)close(config_pipe[0]);
        return 71;
    }
    config_pipe[1] = -1;
    if (move_descriptor(config_pipe[0], AGENTBOX_WAW_BRIDGE_CONFIG_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_PROJECT_DIRECTORY],
                        AGENTBOX_WAW_BRIDGE_PROJECT_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_SELECTED_HOME_DIRECTORY],
                        AGENTBOX_WAW_BRIDGE_HOME_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_TEMP_DIRECTORY], AGENTBOX_WAW_BRIDGE_TEMP_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_VENDOR_EXECUTABLE],
                        AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_POLICY_DIRECTORY], AGENTBOX_WAW_BRIDGE_POLICY_FD) != 0 ||
        move_descriptor(safe[AGENTBOX_WAW_FD_WBR_ENDPOINT], AGENTBOX_WAW_BRIDGE_WBR_FD) != 0) {
        close_received(safe);
        (void)close(config_pipe[0]);
        return 71;
    }
    kept[0] = AGENTBOX_WAW_BRIDGE_CONFIG_FD;
    kept[1] = AGENTBOX_WAW_BRIDGE_PROJECT_FD;
    kept[2] = AGENTBOX_WAW_BRIDGE_HOME_FD;
    kept[3] = AGENTBOX_WAW_BRIDGE_TEMP_FD;
    kept[4] = AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD;
    kept[5] = AGENTBOX_WAW_BRIDGE_POLICY_FD;
    kept[6] = AGENTBOX_WAW_BRIDGE_WBR_FD;
    kept[7] = safe[AGENTBOX_WAW_FD_BRIDGE_EXECUTABLE];
    kept[8] = AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD;
    if (agentbox_waw_set_cloexec(AGENTBOX_WAW_BOOTSTRAP_CONTROL_FD, 0) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0 ||
        agentbox_waw_apply_basic_limits() != 0) {
        return 71;
    }
    return agentbox_waw_launch_isolated(&config, safe[AGENTBOX_WAW_FD_BRIDGE_EXECUTABLE],
                                        bridge_argv, bridge_env);
}

static int run_auth_probe(void) {
    unsigned char raw[AGENTBOX_WAW_AUTH_RECORD_BYTES];
    struct agentbox_waw_auth_probe_config config;
    uint32_t runtime_pid = 0U;
    pid_t expected_parent = getppid();
    int kept[] = {AGENTBOX_WAW_AUTH_CONTROL_FD, AGENTBOX_WAW_AUTH_CGROUP_FD,
                  AGENTBOX_WAW_AUTH_VENDOR_EXECUTABLE_FD, AGENTBOX_WAW_AUTH_HOME_FD,
                  AGENTBOX_WAW_AUTH_SCRATCH_FD, AGENTBOX_WAW_AUTH_POLICY_FD};
    size_t index;
    if (expected_parent <= 1 || (uintmax_t)expected_parent > (uintmax_t)UINT32_MAX ||
        prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != expected_parent ||
        receive_auth_record(raw) != 0 || parse_auth_record(raw, &config, &runtime_pid) != 0 ||
        runtime_pid != (uint32_t)expected_parent || config.runtime_uid != (uint32_t)geteuid() ||
        config.runtime_gid != (uint32_t)getegid() ||
        validate_auth_peer(runtime_pid, config.runtime_uid, config.runtime_gid) != 0 ||
        validate_auth_roles(&config) != 0 ||
        getppid() != expected_parent) {
        return 65;
    }
    for (index = 0; index < sizeof(kept) / sizeof(kept[0]); ++index) {
        if (agentbox_waw_set_cloexec(kept[index], 1) != 0) {
            return 71;
        }
    }
    if (place_self_in_cgroup(AGENTBOX_WAW_AUTH_CGROUP_FD) != 0 ||
        validate_auth_cgroup_marker(config.workspace_hash, config.generation) != 0 ||
        agentbox_waw_close_except(kept, sizeof(kept) / sizeof(kept[0])) != 0 ||
        agentbox_waw_apply_basic_limits() != 0 ||
        agentbox_waw_send_auth_placed(AGENTBOX_WAW_AUTH_CONTROL_FD) != 0 ||
        close(AGENTBOX_WAW_AUTH_CONTROL_FD) != 0) {
        return 71;
    }
    return agentbox_waw_launch_auth_probe(&config);
}

int main(int argc, char **argv) {
    enum agentbox_waw_agent_type agent;
    uint64_t runtime_pid;
    uint64_t bootstrap_fd;
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-pane-bootstrap " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    if (argc == 2 && strcmp(argv[1], "--auth-probe") == 0) {
        return run_auth_probe();
    }
    if (argc == 10 && strcmp(argv[1], "--launch-tmux") == 0 &&
        strcmp(argv[2], "--workspace-hash") == 0 &&
        agentbox_waw_is_hex_digest(argv[3]) && strcmp(argv[4], "--agent-type") == 0 &&
        agentbox_waw_parse_agent(argv[5], &agent) == 0 &&
        strcmp(argv[6], "--runtime-pid") == 0 &&
        parse_cli_positive(argv[7], (uint64_t)INT_MAX, &runtime_pid) == 0 &&
        strcmp(argv[8], "--bootstrap-fd") == 0 &&
        parse_cli_positive(argv[9], (uint64_t)INT_MAX, &bootstrap_fd) == 0) {
        return launch_tmux(argv[3], agent, (int)runtime_pid, (int)bootstrap_fd);
    }
    if (argc != 5 || strcmp(argv[1], "--workspace-hash") != 0 ||
        !agentbox_waw_is_hex_digest(argv[2]) || strcmp(argv[3], "--agent-type") != 0 ||
        agentbox_waw_parse_agent(argv[4], &agent) != 0) {
        return 64;
    }
    return run_bootstrap(argv[2], agent);
}

#else

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        (void)puts("agentbox-waw-pane-bootstrap " AGENTBOX_WAW_NATIVE_VERSION);
        return 0;
    }
    (void)argv;
    return 78;
}

#endif
