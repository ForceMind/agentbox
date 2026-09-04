#define _GNU_SOURCE

#include "waw_isolation.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#if defined(__linux__) && !defined(AGENTBOX_WAW_PORTABLE_CHECK)

#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/landlock.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <sched.h>
#include <sys/prctl.h>
#include <sys/syscall.h>

static int write_file(const char *path, const char *value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    size_t size = strlen(value);
    int result;
    if (fd < 0) {
        return -1;
    }
    result = agentbox_waw_write_exact(fd, value, size);
    if (close(fd) != 0) {
        result = -1;
    }
    return result;
}

static int write_user_maps(pid_t child, uid_t host_uid, gid_t host_gid) {
    char path[64];
    char mapping[96];
    int length;
    length = snprintf(path, sizeof(path), "/proc/%ld/setgroups", (long)child);
    if (length < 0 || (size_t)length >= sizeof(path) || write_file(path, "deny\n") != 0) {
        return -1;
    }
    length = snprintf(path, sizeof(path), "/proc/%ld/uid_map", (long)child);
    if (length < 0 || (size_t)length >= sizeof(path)) {
        return -1;
    }
    length = snprintf(mapping, sizeof(mapping), "%u %u 1\n", (unsigned int)AGENTBOX_WAW_INNER_UID,
                      (unsigned int)host_uid);
    if (length < 0 || (size_t)length >= sizeof(mapping) || write_file(path, mapping) != 0) {
        return -1;
    }
    length = snprintf(path, sizeof(path), "/proc/%ld/gid_map", (long)child);
    if (length < 0 || (size_t)length >= sizeof(path)) {
        return -1;
    }
    length = snprintf(mapping, sizeof(mapping), "%u %u 1\n", (unsigned int)AGENTBOX_WAW_INNER_GID,
                      (unsigned int)host_gid);
    return length < 0 || (size_t)length >= sizeof(mapping) ? -1 : write_file(path, mapping);
}

static int ensure_directory(const char *path, mode_t mode) {
    if (mkdir(path, mode) != 0 && errno != EEXIST) {
        return -1;
    }
    return 0;
}

static int bind_descriptor(int fd, const char *target, int read_only) {
    char source[32];
    unsigned long flags = MS_BIND | MS_REC;
    int length = snprintf(source, sizeof(source), "/proc/self/fd/%d", fd);
    if (length < 0 || (size_t)length >= sizeof(source) || mount(source, target, NULL, flags, NULL) != 0) {
        return -1;
    }
    flags = MS_BIND | MS_REMOUNT | MS_NOSUID | MS_NODEV;
    if (read_only != 0) {
        flags |= MS_RDONLY;
    }
    return mount(NULL, target, NULL, flags, NULL);
}

static int mask_existing(const char *target, const char *mask_directory, const char *mask_file) {
    struct stat status;
    const char *source;
    if (lstat(target, &status) != 0) {
        return errno == ENOENT ? 0 : -1;
    }
    source = S_ISDIR(status.st_mode) ? mask_directory : mask_file;
    return mount(source, target, NULL, MS_BIND, NULL);
}

static int setup_mounts(const struct agentbox_waw_bridge_config *config) {
    const char *agent = agentbox_waw_agent_name((enum agentbox_waw_agent_type)config->agent_type);
    const char *other = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE ? "codex" : "claude";
    const char *policy = config->agent_type == (uint8_t)AGENTBOX_WAW_AGENT_CLAUDE
                             ? "/etc/claude-code"
                             : "/etc/codex";
    char workspace_root[160];
    char project_target[176];
    char temp_target[176];
    char mask_directory[176];
    char mask_file[176];
    char home_target[128];
    char other_home[128];
    char launch_target[176];
    int mask_fd;
    int length;
    static const char *const fixed_masks[] = {
        "/var/lib/agentbox-waw/runtime-epoch-v1",
        "/var/lib/agentbox-waw/runtime-attestation-x25519.key",
        "/var/lib/agentbox-waw/runtime-attestation-x25519.pub",
        "/var/lib/agentbox-waw/runtime-host-installation.v2.json",
        "/var/lib/agentbox-waw/bindings-v1",
        "/var/lib/agentbox-waw/workspace-attestations-v1",
        "/var/lib/agentbox-waw/cgroup-attestations-v1",
        "/home/agentbox-runtime/.local/share/agentbox/provider-secrets/v1",
        "/run/agentbox-waw/workspace-control.sock",
        "/run/agentbox-waw/workspace-stream.sock",
        "/run/agentbox-waw/tmux",
        "/root",
    };
    size_t index;
    if (agent == NULL || mount(NULL, "/", NULL, MS_REC | MS_PRIVATE, NULL) != 0) {
        return -1;
    }
    length = snprintf(workspace_root, sizeof(workspace_root), AGENTBOX_WAW_RUN_ROOT "/tmp/%s",
                      config->workspace_hash);
    if (length < 0 || (size_t)length >= sizeof(workspace_root)) {
        return -1;
    }
    length = snprintf(project_target, sizeof(project_target), "%s/project", workspace_root);
    if (length < 0 || (size_t)length >= sizeof(project_target)) {
        return -1;
    }
    length = snprintf(temp_target, sizeof(temp_target), "%s/vendor", workspace_root);
    if (length < 0 || (size_t)length >= sizeof(temp_target)) {
        return -1;
    }
    length = snprintf(mask_directory, sizeof(mask_directory), "%s/masked", workspace_root);
    if (length < 0 || (size_t)length >= sizeof(mask_directory)) {
        return -1;
    }
    length = snprintf(mask_file, sizeof(mask_file), "%s/masked-file", workspace_root);
    if (length < 0 || (size_t)length >= sizeof(mask_file)) {
        return -1;
    }
    length = snprintf(home_target, sizeof(home_target), AGENTBOX_WAW_STATE_ROOT "/vendor-homes/%s",
                      agent);
    if (length < 0 || (size_t)length >= sizeof(home_target)) {
        return -1;
    }
    length = snprintf(other_home, sizeof(other_home), AGENTBOX_WAW_STATE_ROOT "/vendor-homes/%s",
                      other);
    if (length < 0 || (size_t)length >= sizeof(other_home) ||
        ensure_directory(project_target, 0700) != 0 || ensure_directory(temp_target, 0700) != 0 ||
        ensure_directory(mask_directory, 0700) != 0 || chmod(mask_directory, 0700) != 0) {
        return -1;
    }
    if (chmod(mask_file, 0600) != 0 && errno != ENOENT) {
        return -1;
    }
    mask_fd = open(mask_file, O_WRONLY | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (mask_fd < 0 || close(mask_fd) != 0 ||
        bind_descriptor(AGENTBOX_WAW_BRIDGE_PROJECT_FD, project_target, 0) != 0 ||
        bind_descriptor(AGENTBOX_WAW_BRIDGE_HOME_FD, home_target, 0) != 0 ||
        bind_descriptor(AGENTBOX_WAW_BRIDGE_TEMP_FD, temp_target, 0) != 0 ||
        bind_descriptor(AGENTBOX_WAW_BRIDGE_POLICY_FD, policy, 1) != 0) {
        return -1;
    }
    for (index = 0; index < sizeof(fixed_masks) / sizeof(fixed_masks[0]); ++index) {
        if (mask_existing(fixed_masks[index], mask_directory, mask_file) != 0) {
            return -1;
        }
    }
    length = snprintf(launch_target, sizeof(launch_target), "%s/launch.v1.sock", workspace_root);
    if (length < 0 || (size_t)length >= sizeof(launch_target) ||
        mask_existing(launch_target, mask_directory, mask_file) != 0 ||
        mask_existing(other_home, mask_directory, mask_file) != 0 ||
        chmod(mask_directory, 0000) != 0 || chmod(mask_file, 0000) != 0 ||
        chdir(project_target) != 0 ||
        umount2("/proc", MNT_DETACH) != 0 ||
        mount("proc", "/proc", "proc", MS_NOSUID | MS_NODEV | MS_NOEXEC,
              "hidepid=2,subset=pid") != 0) {
        return -1;
    }
    return 0;
}

static uint64_t landlock_base_rights(void) {
    uint64_t rights = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_WRITE_FILE |
                      LANDLOCK_ACCESS_FS_READ_FILE | LANDLOCK_ACCESS_FS_READ_DIR |
                      LANDLOCK_ACCESS_FS_REMOVE_DIR | LANDLOCK_ACCESS_FS_REMOVE_FILE |
                      LANDLOCK_ACCESS_FS_MAKE_CHAR | LANDLOCK_ACCESS_FS_MAKE_DIR |
                      LANDLOCK_ACCESS_FS_MAKE_REG | LANDLOCK_ACCESS_FS_MAKE_SOCK |
                      LANDLOCK_ACCESS_FS_MAKE_FIFO | LANDLOCK_ACCESS_FS_MAKE_BLOCK |
                      LANDLOCK_ACCESS_FS_MAKE_SYM;
#ifdef LANDLOCK_ACCESS_FS_REFER
    rights |= LANDLOCK_ACCESS_FS_REFER;
#endif
#ifdef LANDLOCK_ACCESS_FS_TRUNCATE
    rights |= LANDLOCK_ACCESS_FS_TRUNCATE;
#endif
    return rights;
}

static int add_landlock_path(int ruleset, const char *path, uint64_t access) {
    struct landlock_path_beneath_attr rule;
    int fd = open(path, O_PATH | O_CLOEXEC);
    int result;
    if (fd < 0) {
        return errno == ENOENT ? 0 : -1;
    }
    memset(&rule, 0, sizeof(rule));
    rule.allowed_access = access;
    rule.parent_fd = fd;
    result = (int)syscall(SYS_landlock_add_rule, ruleset, LANDLOCK_RULE_PATH_BENEATH, &rule, 0U);
    (void)close(fd);
    return result;
}

static int add_landlock_fd(int ruleset, int fd, uint64_t access) {
    struct landlock_path_beneath_attr rule;
    memset(&rule, 0, sizeof(rule));
    rule.allowed_access = access;
    rule.parent_fd = fd;
    return (int)syscall(SYS_landlock_add_rule, ruleset, LANDLOCK_RULE_PATH_BENEATH, &rule, 0U);
}

static int apply_landlock(const struct agentbox_waw_bridge_config *config, int bridge_executable) {
#if defined(SYS_landlock_create_ruleset) && defined(SYS_landlock_add_rule) && defined(SYS_landlock_restrict_self)
    struct landlock_ruleset_attr ruleset_attr;
    uint64_t rights = landlock_base_rights();
    uint64_t read_only = LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE |
                         LANDLOCK_ACCESS_FS_READ_DIR;
    char project[176];
    char home[128];
    char temporary[176];
    const char *agent = agentbox_waw_agent_name((enum agentbox_waw_agent_type)config->agent_type);
    int abi = (int)syscall(SYS_landlock_create_ruleset, NULL, 0U, LANDLOCK_CREATE_RULESET_VERSION);
    int ruleset;
    int length;
    static const char *const system_paths[] = {"/usr", "/bin", "/lib", "/lib64", "/etc", "/dev", "/proc"};
    size_t index;
    if (abi < 1 || agent == NULL) {
        return -1;
    }
#ifdef LANDLOCK_ACCESS_FS_REFER
    if (abi < 2) {
        rights &= ~((uint64_t)LANDLOCK_ACCESS_FS_REFER);
    }
#endif
#ifdef LANDLOCK_ACCESS_FS_TRUNCATE
    if (abi < 3) {
        rights &= ~((uint64_t)LANDLOCK_ACCESS_FS_TRUNCATE);
    }
#endif
    memset(&ruleset_attr, 0, sizeof(ruleset_attr));
    ruleset_attr.handled_access_fs = rights;
    ruleset = (int)syscall(SYS_landlock_create_ruleset, &ruleset_attr, sizeof(ruleset_attr), 0U);
    if (ruleset < 0) {
        return -1;
    }
    length = snprintf(project, sizeof(project), AGENTBOX_WAW_RUN_ROOT "/tmp/%s/project",
                      config->workspace_hash);
    if (length < 0 || (size_t)length >= sizeof(project)) {
        (void)close(ruleset);
        return -1;
    }
    length = snprintf(temporary, sizeof(temporary), AGENTBOX_WAW_RUN_ROOT "/tmp/%s/vendor",
                      config->workspace_hash);
    if (length < 0 || (size_t)length >= sizeof(temporary)) {
        (void)close(ruleset);
        return -1;
    }
    length = snprintf(home, sizeof(home), AGENTBOX_WAW_STATE_ROOT "/vendor-homes/%s", agent);
    if (length < 0 || (size_t)length >= sizeof(home)) {
        (void)close(ruleset);
        return -1;
    }
    for (index = 0; index < sizeof(system_paths) / sizeof(system_paths[0]); ++index) {
        uint64_t allowed = strcmp(system_paths[index], "/dev") == 0
                               ? read_only | LANDLOCK_ACCESS_FS_WRITE_FILE
                               : read_only;
        if (add_landlock_path(ruleset, system_paths[index], allowed) != 0) {
            (void)close(ruleset);
            return -1;
        }
    }
    if (add_landlock_path(ruleset, project, rights) != 0 ||
        add_landlock_path(ruleset, home, rights) != 0 ||
        add_landlock_path(ruleset, temporary, rights) != 0 ||
        add_landlock_fd(ruleset, bridge_executable,
                        LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE) != 0 ||
        add_landlock_fd(ruleset, AGENTBOX_WAW_BRIDGE_VENDOR_EXECUTABLE_FD,
                        LANDLOCK_ACCESS_FS_EXECUTE | LANDLOCK_ACCESS_FS_READ_FILE) != 0 ||
        prctl(PR_SET_NO_NEW_PRIVS, 1UL, 0UL, 0UL, 0UL) != 0 ||
        syscall(SYS_landlock_restrict_self, ruleset, 0U) != 0L) {
        (void)close(ruleset);
        return -1;
    }
    return close(ruleset);
#else
    (void)config;
    errno = ENOTSUP;
    return -1;
#endif
}

static int apply_seccomp(void) {
    int denied[32];
    size_t denied_count = 0;
    struct sock_filter filters[72];
    struct sock_fprog program;
    size_t index = 0;
#define DENY_SYSCALL(name) do { denied[denied_count++] = SYS_##name; } while (0)
#ifdef SYS_setns
    DENY_SYSCALL(setns);
#endif
#ifdef SYS_unshare
    DENY_SYSCALL(unshare);
#endif
#ifdef SYS_mount
    DENY_SYSCALL(mount);
#endif
#ifdef SYS_umount2
    DENY_SYSCALL(umount2);
#endif
#ifdef SYS_pivot_root
    DENY_SYSCALL(pivot_root);
#endif
#ifdef SYS_open_by_handle_at
    DENY_SYSCALL(open_by_handle_at);
#endif
#ifdef SYS_ptrace
    DENY_SYSCALL(ptrace);
#endif
#ifdef SYS_process_vm_readv
    DENY_SYSCALL(process_vm_readv);
#endif
#ifdef SYS_process_vm_writev
    DENY_SYSCALL(process_vm_writev);
#endif
#ifdef SYS_bpf
    DENY_SYSCALL(bpf);
#endif
#ifdef SYS_perf_event_open
    DENY_SYSCALL(perf_event_open);
#endif
#ifdef SYS_keyctl
    DENY_SYSCALL(keyctl);
#endif
#ifdef SYS_add_key
    DENY_SYSCALL(add_key);
#endif
#ifdef SYS_request_key
    DENY_SYSCALL(request_key);
#endif
#ifdef SYS_open_tree
    DENY_SYSCALL(open_tree);
#endif
#ifdef SYS_move_mount
    DENY_SYSCALL(move_mount);
#endif
#ifdef SYS_fsopen
    DENY_SYSCALL(fsopen);
#endif
#ifdef SYS_fsconfig
    DENY_SYSCALL(fsconfig);
#endif
#ifdef SYS_fsmount
    DENY_SYSCALL(fsmount);
#endif
#ifdef SYS_mount_setattr
    DENY_SYSCALL(mount_setattr);
#endif
#undef DENY_SYSCALL
#if defined(__x86_64__)
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                                                     offsetof(struct seccomp_data, arch));
    filters[index++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,
                                                     AUDIT_ARCH_X86_64, 1U, 0U);
#elif defined(__aarch64__)
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                                                     offsetof(struct seccomp_data, arch));
    filters[index++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,
                                                     AUDIT_ARCH_AARCH64, 1U, 0U);
#else
    errno = ENOTSUP;
    return -1;
#endif
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS);
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                                                     offsetof(struct seccomp_data, nr));
#ifdef SYS_clone3
    filters[index++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,
                                                     (uint32_t)SYS_clone3, 0U, 1U);
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K,
                                                     SECCOMP_RET_ERRNO | (uint32_t)ENOSYS);
#endif
#ifdef SYS_clone
    filters[index++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,
                                                     (uint32_t)SYS_clone, 0U, 3U);
    filters[index++] = (struct sock_filter)BPF_STMT(
        BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0]));
    filters[index++] = (struct sock_filter)BPF_JUMP(
        BPF_JMP | BPF_JSET | BPF_K,
        (uint32_t)(CLONE_NEWUSER | CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWIPC), 0U, 1U);
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K,
                                                     SECCOMP_RET_ERRNO | (uint32_t)EPERM);
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_LD | BPF_W | BPF_ABS,
                                                     offsetof(struct seccomp_data, nr));
#endif
    for (size_t denied_index = 0; denied_index < denied_count; ++denied_index) {
        filters[index++] = (struct sock_filter)BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K,
                                                         (uint32_t)denied[denied_index], 0U, 1U);
        filters[index++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K,
                                                         SECCOMP_RET_ERRNO | (uint32_t)EPERM);
    }
    filters[index++] = (struct sock_filter)BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW);
    program.len = (unsigned short)index;
    program.filter = filters;
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program);
}

static int child_status(int status) {
    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    }
    if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 125;
}

static void namespace_builder(const struct agentbox_waw_bridge_config *config,
                              int bridge_executable, char *const argv[], char *const envp[],
                              int ready_write, int mapped_read) {
    unsigned char byte = 1U;
    pid_t inner;
    pid_t expected_parent = getppid();
    int builder_pidfd;
    int status;
    if (expected_parent <= 1 || prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 ||
        getppid() != expected_parent ||
        unshare(CLONE_NEWUSER) != 0 ||
        agentbox_waw_write_exact(ready_write, &byte, sizeof(byte)) != 0 ||
        agentbox_waw_read_exact(mapped_read, &byte, sizeof(byte)) != 0 || byte != 1U ||
        setresgid((gid_t)AGENTBOX_WAW_INNER_GID, (gid_t)AGENTBOX_WAW_INNER_GID,
                  (gid_t)AGENTBOX_WAW_INNER_GID) != 0 ||
        setresuid((uid_t)AGENTBOX_WAW_INNER_UID, (uid_t)AGENTBOX_WAW_INNER_UID,
                  (uid_t)AGENTBOX_WAW_INNER_UID) != 0 ||
        (builder_pidfd = agentbox_waw_pidfd_open((int)getpid())) < 0 ||
        unshare(CLONE_NEWNS | CLONE_NEWPID | CLONE_NEWIPC) != 0) {
        _exit(71);
    }
    (void)close(ready_write);
    (void)close(mapped_read);
    inner = fork();
    if (inner < 0) {
        _exit(71);
    }
    if (inner == 0) {
        struct pollfd parent_alive;
        parent_alive.fd = builder_pidfd;
        parent_alive.events = POLLIN;
        parent_alive.revents = 0;
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || poll(&parent_alive, 1U, 0) != 0 ||
            getpid() != 1 ||
            setup_mounts(config) != 0 || apply_landlock(config, bridge_executable) != 0 ||
            agentbox_waw_apply_no_new_privs() != 0 || apply_seccomp() != 0) {
            _exit(71);
        }
        (void)close(builder_pidfd);
        (void)agentbox_waw_exec_held(bridge_executable, argv, envp);
        _exit(71);
    }
    (void)close(builder_pidfd);
    while (waitpid(inner, &status, 0) < 0) {
        if (errno != EINTR) {
            _exit(71);
        }
    }
    _exit(child_status(status));
}

int agentbox_waw_launch_isolated(const struct agentbox_waw_bridge_config *config,
                                 int bridge_executable, char *const argv[], char *const envp[]) {
    int ready_pipe[2];
    int mapped_pipe[2];
    pid_t child;
    unsigned char byte;
    int status;
    if (pipe2(ready_pipe, O_CLOEXEC) != 0 || pipe2(mapped_pipe, O_CLOEXEC) != 0) {
        return 71;
    }
    child = fork();
    if (child < 0) {
        return 71;
    }
    if (child == 0) {
        (void)close(ready_pipe[0]);
        (void)close(mapped_pipe[1]);
        namespace_builder(config, bridge_executable, argv, envp, ready_pipe[1], mapped_pipe[0]);
    }
    (void)close(ready_pipe[1]);
    (void)close(mapped_pipe[0]);
    if (agentbox_waw_read_exact(ready_pipe[0], &byte, sizeof(byte)) != 0 || byte != 1U ||
        write_user_maps(child, geteuid(), getegid()) != 0 ||
        agentbox_waw_write_exact(mapped_pipe[1], &byte, sizeof(byte)) != 0) {
        (void)kill(child, SIGKILL);
    }
    (void)close(ready_pipe[0]);
    (void)close(mapped_pipe[1]);
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) {
            return 71;
        }
    }
    return child_status(status);
}

#else

int agentbox_waw_launch_isolated(const struct agentbox_waw_bridge_config *config,
                                 int bridge_executable, char *const argv[], char *const envp[]) {
    (void)config;
    (void)bridge_executable;
    (void)argv;
    (void)envp;
    return 78;
}

#endif
