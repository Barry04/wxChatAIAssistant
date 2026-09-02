import { Section } from "reacticle";

// 第四节：待确认回复中心 —— source.md「新版能力」第 3 条。
// 正文为主体，无额外语义组件。
export function SectionConfirmationCenter() {
  return (
    <Section index="04" title="待确认回复中心">
      <p>
        通过审核的候选不会直接变成消息，而是进入<strong>待确认回复中心</strong>——一个专门给人
        做最终决定的地方。它<strong>默认按当前会话过滤</strong>，让你只看手头正在处理的这段对话；
        需要全局视角时，也可以<strong>切换查看全部会话</strong>。
      </p>
      <p>
        在中心里，你可以<strong>逐条查看上下文、修改候选</strong>——机器生成的措辞只是起点，
        最终措辞由你决定。改到满意后，<strong>确认</strong>这一步才把批准文本交给发送执行器。
      </p>
      <p>
        这个「确认」动作是整个系统的关键闸门：草稿可以随便生成，但<strong>离开待确认中心、
        走向发送的，必须是一条被人工批准过的文本</strong>。它把「生成」与「发送」在流程上彻底
        分开——这正是 README 里「默认不发送消息」能成立的执行基础。
      </p>
    </Section>
  );
}
