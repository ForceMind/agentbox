# Owner Commands

## 查看状态

“告诉我 AgentBox 当前真实状态。”先查询 Git/GitHub，不修改文件。

## 继续

“继续项目。”只执行 `NEXT_ACTION` 中当前仍被授权的动作，并停在下一个 Owner gate。

## 审查

“对当前 PR 做独立 Architecture/Security/Test Review。”使用 read-only subagents，不能 rubber-stamp。

## 修复

“修复当前 Review 中属于已授权范围的 blockers。”不得扩大 Slice。

## 准备授权

“生成一条绑定 PR number、exact head、exact base 的 Owner approval statement，但不要执行 Ready 或 merge。”

## 授权合并

示例：

```text
Owner Merge Authorization: GRANTED
PR: #41
Authorized Head: <exact head>
Authorized Base: <exact base>
Merge Method: Squash
```

只有 Owner 明确发送后才执行，并在 merge 后 exact read-back。

## 暂停

“停止所有写操作，保持 branch/PR，不开始下一阶段。”
