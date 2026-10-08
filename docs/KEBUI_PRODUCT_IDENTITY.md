# Kebui 产品标识层

状态：有界实现候选；2026-10-07。

依据[品牌规范](project/KEBUI_BRAND.md)及[产品计划 K1](project/KEBUI_PRODUCT_PLAN.md)，
本批将现有工作台的产品名称落实为 Kebui（科布），不新增产品能力。

## 范围与兼容性

- README 首屏与品牌/兼容说明；Web 外壳、登录产品简介、页面标题及静态 HTML 元数据。
- 两种语言均使用 `Kebui` 作为主标识；中文产品简介使用 `Kebui（科布）`。
- 现有图标保留，不将通用图标冒称已经验收的新 logo；U1 设计与原型仍待交付。
- API `name: AgentBox`、CLI、Runtime、包/服务/数据库名、存储键、文件名、安装路径和
  历史 Project 示例名保持原值。现有旧链接不失效。
- Logs/Doctor 中的 AgentBox 技术组件名及登录的 AgentBox CLI 指引保留。
- 无 Chat/Task/路由能力扩展，无域名所有权主张，无版本、发行、部署或 host 激活。

## 基线证据

PR161 正常合并为 `8027628f2cf9937d65626e8a9e87eed2f59c7675`，tree
`de3a2410de75159f3b33acbefbdec4913b18b3f6` 与合格 head14211671 完全一致。
该 exact-main 六套 workflow 均 completed/success：Frontend37660978852、
Backend37660978927、E2E37660979034、Security37660978873、Deployment37660978847、
Release Candidate37660978895。该证据只证明基线，不替代本批新 head 验证。

## 验收

品牌与标题断言、API 原名称兼容、完整 Web 检查及新 exact-head CI 分别记录。
只修改现有 E2E 标题的产品后缀和登录标题，保留其导航、身份、生命周期断言与
合成 Project 名。浏览器与截图以新 head 实际执行结果为准，不继承旧图的品牌资格。

### 本地候选验证

实际执行 Web vitest 全量：87 文件、1972 测试通过；ESLint、TypeScript、Vite build、
Prettier 检查通过。文档链接 861 项、四键 YAML、secret-pattern、source-boundary 与
`git diff --check` 通过。pnpm 包装器最初受 HOME/store 路径阻碍；使用既有安装的
同版本工具直接执行，没有安装新依赖或改 lock。构建仍有既有大 chunk 提示。
后端与 extension 本地全量未重跑，浏览器及六套 CI 仍待新提交验证。
