#ifndef AGENTBOX_WAW_NATIVE_H
#define AGENTBOX_WAW_NATIVE_H

#include "agentbox_waw_protocol.h"

#include <stddef.h>
#include <stdint.h>

#define AGENTBOX_WAW_BRIDGE_CONFIG_MAGIC UINT32_C(0x41425743)

enum agentbox_waw_agent_type {
    AGENTBOX_WAW_AGENT_CLAUDE = 1,
    AGENTBOX_WAW_AGENT_CODEX = 2
};

struct agentbox_waw_bridge_config {
    uint32_t magic;
    uint32_t abi_version;
    uint64_t generation;
    uint32_t runtime_uid;
    uint32_t runtime_gid;
    uint16_t columns;
    uint16_t rows;
    uint8_t agent_type;
    uint8_t reserved[7];
    char workspace_hash[65];
    char profile_digest[65];
};

int agentbox_waw_is_hex_digest(const char *value);
int agentbox_waw_parse_agent(const char *value, enum agentbox_waw_agent_type *agent);
const char *agentbox_waw_agent_name(enum agentbox_waw_agent_type agent);
int agentbox_waw_set_cloexec(int fd, int enabled);
int agentbox_waw_duplicate_high(int fd);
int agentbox_waw_close_except(const int *kept, size_t count);
int agentbox_waw_apply_basic_limits(void);
int agentbox_waw_apply_no_new_privs(void);
int agentbox_waw_pidfd_open(int pid);
int agentbox_waw_exec_held(int fd, char *const argv[], char *const envp[]);
int agentbox_waw_validate_directory_fd(int fd);
int agentbox_waw_validate_regular_fd(int fd);
int agentbox_waw_validate_executable_fd(int fd);
int agentbox_waw_validate_path_directory_fd(int fd);
int agentbox_waw_validate_seqpacket_fd(int fd);
int agentbox_waw_read_exact(int fd, void *buffer, size_t size);
int agentbox_waw_write_exact(int fd, const void *buffer, size_t size);
int agentbox_waw_wait_child(int pid, int pidfd);
int agentbox_waw_confirm_exec(int status_fd, int pidfd);
int agentbox_waw_confirm_exec_timeout(int status_fd, int pidfd, int timeout_ms);
int agentbox_waw_send_ready(int fd);
void agentbox_waw_terminate_and_reap(int pid, int pidfd);

#endif
