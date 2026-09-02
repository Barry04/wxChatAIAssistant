import { Section } from "reacticle";

// 第九节：使用流程 —— source.md「使用流程」5 步（100% 保留，有序列表呈现）。
export function SectionUsageFlow() {
  return (
    <Section index="09" title="使用流程">
      <p>从零开始走一遍，一共五步：</p>
      <ol>
        <li>
          新建联系人，选择 <code>partner</code>、<code>friend</code> 或 <code>family</code>，
          补充称呼和表达偏好。
        </li>
        <li>导入自己的聊天记录，或在演示模式下粘贴一段虚构对话。</li>
        <li>在「手动生成」中产出候选，选择或编辑最终草稿。</li>
        <li>如需监听微信消息，先只启用 dry-run，并从「待确认」工作台逐条审核。</li>
        <li>只有在你明确接受风险并完成相关配置后，才考虑启用真实发送。</li>
      </ol>
      <p>
        注意最后两步的顺序：先 dry-run、后真实发送。<strong>dry-run 是默认状态</strong>——
        监听、生成、审核都可以在完全不出网、不发送的前提下跑通；「启用真实发送」永远是
        你明确做出的最后一步决定。
      </p>
    </Section>
  );
}
