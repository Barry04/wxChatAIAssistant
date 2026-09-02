import { Article, Hero, Lead, Summary, Conclusion, Raw } from "reacticle";
import { SectionOpening } from "./sections/01-opening";
import { SectionContactWorkbench } from "./sections/02-contact-workbench";
import { SectionDraftPipeline } from "./sections/03-draft-pipeline";
import { SectionConfirmationCenter } from "./sections/04-confirmation-center";
import { SectionAutomationChain } from "./sections/05-automation-chain";
import { SectionLocalDemo } from "./sections/06-local-demo";
import { SectionSecurityModel } from "./sections/07-security-model";
import { SectionQuickStart } from "./sections/08-quick-start";
import { SectionUsageFlow } from "./sections/09-usage-flow";
import { SectionPrivacy } from "./sections/10-privacy";
import { SectionTroubleshooting } from "./sections/11-troubleshooting";
import { SectionChecks } from "./sections/12-checks";
import { SectionProjectStructure } from "./sections/13-project-structure";
import { SectionFurtherReading } from "./sections/14-further-reading";

// Article.tsx is the ASSEMBLER, owned by the main agent. It imports and orders
// Section components — it must NOT contain Section bodies inline.
//
// 铁律：每个 Section 是独立组件文件（article/sections/NN-*.tsx），坚决不允许把
// 多个 Section 直接写进这里。这样多个 Agent 才能并行各写一个 section 文件，主 Agent
// 在这里负责合并与稳定性。详见 references/section-build.md。
//
// width (narrow/regular/wide/full) + toc 在 Plan Checkpoint 确认，与主题解耦
// （见 references/layout.md）。
export function ArticleDoc() {
  return (
    <Article toc width="wide">
      <Hero
        title="wxChatAIAssistant"
        subtitle="本地优先的关系型微信 AI 聊天助手"
        meta={[
          { label: "项目", value: "README 精读" },
          { label: "来源", value: "F:\\wxChatAssistant" },
        ]}
      />
      <Lead>
        它把「按联系人关系写回复」做成一个本地、可审计、默认不自动发送的工作台：草稿由多角色
        Agent 生成，发送由无模型的 Operator 执行，个人数据默认留在自己的电脑上。
      </Lead>

      <Summary
        title="结论先行"
        points={[
          "草稿由 understand → style → writer → reviewer 多角色 Agent 依次生成与审核。",
          "发送能力与草稿能力物理隔离：真实发送只由无模型的 Operator 执行，且必须已有批准的原文。",
          "自动回复默认关闭、默认 dry-run；L1/L2 必须人工确认，L3 直接拦截。",
          "微信读取、画像、设置与运行记录默认都留在本机 data/ 目录，不会上传。",
        ]}
      />

      <SectionOpening />
      <SectionContactWorkbench />
      <SectionDraftPipeline />
      <SectionConfirmationCenter />
      <SectionAutomationChain />
      <SectionLocalDemo />
      <SectionSecurityModel />
      <SectionQuickStart />
      <SectionUsageFlow />
      <SectionPrivacy />
      <SectionTroubleshooting />
      <SectionChecks />
      <SectionProjectStructure />
      <SectionFurtherReading />

      <Conclusion
        title="一句话收束"
        takeaways={[
          "它把「按关系写回复」做成一件本地、可审计、默认不自动发送的事——数据留在本机，发送必须经人确认。",
          "安全由结构保证：草稿生成与发送执行分离，风险分级决定放行路径，任何一环都没有越权发送的能力。",
          "默认 dry-run：从监听、生成到审核可以完全离线跑通；真实发送永远是你明确做出的最后一步。",
          "想上手，按「快速开始」三步启动；想深入，读「进一步阅读」里的架构、命令与设计文档。",
        ]}
      />

      {/*
        ─── Colophon ───
        每篇 Beautiful Article 必须保留这一段，位置在 </Article> 之前、所有 Section /
        Conclusion 之后。它是文章的"印记"，告诉读者文章是用什么工作流生成的。

        约束：
          • 不要删除。不要移到 Hero 旁边或浮动到角落。
          • 文本格式固定：Made with beautiful-article（带链接到 github 仓库）· <主题> theme
          • 主题名（下方 tufte 占位）由 scaffold 写入；切换主题时同步更新这里和
            main.tsx 的 <ThemeProvider theme="...">。
          • 样式只能用 --ra-* token，跟随主题自适应；保持低对比、小字、居中。
      */}
      <Raw title="">
        <footer
          style={{
            marginTop: "var(--ra-space-7, 3rem)",
            paddingTop: "var(--ra-space-4, 1rem)",
            borderTop: "1px solid var(--ra-color-border, currentColor)",
            color: "var(--ra-color-muted, inherit)",
            fontSize: "var(--ra-text-xs, 0.78rem)",
            textAlign: "center",
            letterSpacing: "0.02em",
            opacity: 0.85,
          }}
        >
          Made with{" "}
          <a
            href="https://github.com/ConardLi/garden-skills"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: "inherit",
              textDecoration: "underline",
              textUnderlineOffset: "0.2em",
            }}
          >
            beautiful-article
          </a>{" "}
          · tufte theme
        </footer>
      </Raw>
    </Article>
  );
}
