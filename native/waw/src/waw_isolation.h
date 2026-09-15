#ifndef AGENTBOX_WAW_ISOLATION_H
#define AGENTBOX_WAW_ISOLATION_H

#include "waw_native.h"

int agentbox_waw_launch_isolated(const struct agentbox_waw_bridge_config *config,
                                 int bridge_executable, char *const argv[],
                                 char *const envp[]);
int agentbox_waw_launch_auth_probe(const struct agentbox_waw_auth_probe_config *config);

#endif
