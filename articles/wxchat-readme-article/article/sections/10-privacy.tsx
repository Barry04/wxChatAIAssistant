import { Section, Aside } from "reacticle";

// 第十节：本地数据与隐私 —— source.md「本地数据与隐私」整节。
// 正文 + data/ 五项清单（正文列表）+ Aside warning（仓库红线清单）。
export function SectionPrivacy() {
  return (
    <Section index="10" title="本地数据与隐私">
      <p>
        「本地优先」落到磁盘上，就是 <code>data/</code> 目录。个人数据默认都放在这里，
        不进云端、不上传：
      </p>
      <ul>
        <li>
          <code>data/config.sqlite3</code>：联系人、模型和自动回复设置。
        </li>
        <li>
          <code>data/messages.jsonl</code>、<code>data/feedback.jsonl</code>：导入记录与草稿反馈。
        </li>
        <li>
          <code>data/self-skill/</code>：全局、关系和联系人级表达画像。
        </li>
        <li>
          <code>data/automation-state.json</code>、<code>data/automation-events.jsonl</code>：
          自动化状态与动作记录。
        </li>
      </ul>
      <p>
        这五个位置几乎覆盖了全部个人数据：联系人、聊天导入、表达画像、自动化记录。它们
        全部留在本机，也是「公开仓库不应包含个人数据」这条红线的反面——如果这些文件被
        提交进仓库，隐私边界就不存在了。
      </p>

      <Aside tone="warning" label="仓库红线">
        公开仓库不应包含 <code>data/</code>、<code>private/</code>、<code>.runtime/</code>、
        日志、环境变量或私钥。提交前请再次检查暂存区是否含个人数据。
      </Aside>
    </Section>
  );
}
