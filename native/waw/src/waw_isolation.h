#ifndef AGENTBOX_WAW_ISOLATION_H
#define AGENTBOX_WAW_ISOLATION_H

#include "waw_native.h"

int agentbox_waw_launch_isolated(const struct agentbox_waw_bridge_config *config,
                                 int bridge_executable, char *const argv[],
                                 char *const envp[]);

#endif
