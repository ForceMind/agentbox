# R12 API production bootstrap contract

状态：2026-09-08，按Owner已批准的[PRP-v1](project/PRODUCTION_READINESS_PLAN.md)
冻结的R12-A稳定软件契约；R12-B/rc11本地实现、82项定向验证与独立Architecture/
Security/Test复审通过，exact-head CI和merge/read-back待完成。无host/client/key激活。
基线：`1ab28e524d018df3d59e6c48f01646bb1021a978`。

## 固定配置来源

生产API仅从`/etc/agentbox/waw-api-profile.v1.json`读取WAW mode。
不新增Settings/TOML mode字段、环境变量、CLI开关、HTTP route、query或header选择器。
该文件只能包含以下两种canonical UTF-8字节之一，末尾恰好一个LF：

```json
{"mode":"disabled","schema_version":"agentbox-waw-api-profile.v1"}
```

```json
{"mode":"filesystem-v2","schema_version":"agentbox-waw-api-profile.v1"}
```

最大4096 bytes；无BOM、重复/额外字段、大小写别名、空白变体、尾随内容或类型转换。
文件是固定非Secret配置，不携带path、key、host identity、PID、socket或Origin。
解析器映射到既有`WAWMode.DISABLED`与`WAWMode.FILESYSTEM_V2`，不再建立第三套mode。

## 文件验证与兼容性

- 固定root到parent路径使用held `O_DIRECTORY|O_NOFOLLOW`逐级打开；root及`/etc`
  必须root-owned且无group/world写权限。
- `/etc/agentbox`必须匹配现有installer的`root:agentbox 0750`；leaf为
  `root:agentbox 0440`、regular、单hardlink。group ID来自固定系统group，不由调用方配置。
- leaf用`O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK`打开；先核验size再有界读取，
  不阻塞在FIFO/device上，不跟随symlink。读取前后比较descriptor与目录entry及parent链。
- 只有安全parent已验证且leaf确实`ENOENT`时，才按历史安装返回`DISABLED/missing_default`。
  parent不存在/不安全、权限错误、损坏文件、group缺失、替换或读取不一致均失败。
- observation包含mode/source、允许内部使用的identity/digest；不进入HTTP、Audit或日志。
  任何对外失败仅用有界code，不附profile正文、路径、inode或anchor内容。

profile在process启动时读取，作为整个API lifespan的快照；无热重载、TTL或mtime授权。
每级目录entry都通过上级held FD进行nofollow stat，与child FD核验；absence返回前
再次确认leaf ENOENT，不能只fstat一个已被rename到别处的旧parent FD。
构造期间保留可重新核验的observation，在lifespan开始、WAW owner启动/发布前再次核验，
关闭持有资源后才继续；absence observation也要检查leaf没有在启动间隙出现。
发生替换、取消、失败或close不确定时拒绝启动，不能继续使用旧观察或重试可能复用的FD。
安装器变更mode必须配合后续已批准的drain/stop/atomic update/restart/read-back流程。

## API与入口

`create_app`的`waw_mode`变为`WAWMode | None = None`：

| 环境 | 唯一有效来源/行为 |
| --- | --- |
| production | 固定profile；拒绝显式enum mode、注入WAW application或fragmented components |
| test | 保留exact enum和现有exact test-only application；不加载生产profile |
| development | 省略或exact DISABLED；不加载生产profile，FILESYSTEM_V2拒绝 |

production缺profile leaf的旧安装保持关闭；选择FILESYSTEM_V2时只调用一次既有
`WAWAPIApplication.production`，继续既有bind、inventory、singleton、peer和lifespan。
缺anchor/锁/Runtime或cleanup错误必须失败，不静默切回disabled。
disabled不打开anchor、不创造WAW authority；管理readiness仍按既有合同。
`readyz`不表示host qualification；不增加终端准入或Secret的metadata接口。

module级ASGI `app`与console `run()`复用同一installed app及settings，避免第二次profile
读取、重复application/DB构造。显式test factory不共享该单例。
在profile安全核验前不建立新的ControlPlaneServices；构造失败时清理仅本次创建的资源，
不能关闭调用方注入的services。profile observation的所有权由factory移交lifespan，
取消/启动失败有明确close路径；不新增生产callback或可配置loader端口。
整个factory构造/注册段共享一个异常边界，包含HTTP/WebSocket装饰器。owned DB只
清理一次；原factory与DB清理同时失败时保留两项异常，不能吞掉cleanup incomplete。

## Installer后继契约

本批不更改host、unit或配置文件。R12-D实现独立固定更新器：同目录exclusive/no-follow
临时文件，write/fsync、精确owner/mode、基于旧digest的CAS、rename、目录fsync和回读。
首次安装/迁移保持disabled。开启前完成所需资源与获准资格化前置；关闭前先fence并验证
cleanup。失败保留旧配置/管理面，cleanup不确定不能声称切换完成。
固定public anchor及所有Runtime-private资源继续使用现有loader和path，不由profile扩展。

## R12-B所有权与最低验证

API worker拥有`main.py`、新的`waw_deployment_profile.py`及相关API/profile tests；
不修改Settings、installer、Runtime或共享version/workflow。主智能体负责契约、版本和交付。
不重构或放宽现有`waw_host_anchor.py`；可复用其校验模式，但不引入通用filesystem API。

必须验证：两种合法字节；leaf absent；0/4096/4097与有界读取；BOM/UTF-8/字段/尾随拒绝；
symlink/hardlink/FIFO/device、错误uid/gid/mode和parent；读取/构造/启动间替换及absence变化；
cancel/close/error清理；production mode/component注入拒绝；env/TOML不能覆盖；disabled
不加载anchor；一次production factory调用及原生命周期；module app/run复用；既有管理、
test-only WAW、原profile/anchor边界保持。Mac只做定向测试，完整Linux矩阵与独立审查后合并。

完成B只构成software evidence。真实systemd/profile安装、CLI、client与生产资格保持未验证。
