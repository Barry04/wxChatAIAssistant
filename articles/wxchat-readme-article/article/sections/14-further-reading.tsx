import { Section } from "reacticle";

// 第十四节：进一步阅读 —— source.md「进一步阅读」3 个链接（相对路径保留原文）。
export function SectionFurtherReading() {
  return (
    <Section index="14" title="进一步阅读">
      <p>想深入了解设计决策，项目内还有三份文档（相对项目根目录的路径）：</p>
      <ul>
        <li>
          <a href="docs/harness/architecture.md">架构说明</a> —— 系统整体架构与边界。
        </li>
        <li>
          <a href="docs/harness/commands.md">常用命令</a> —— 日常开发与运维命令速查。
        </li>
        <li>
          <a href="docs/relationship-wechat-assistant-design.md">关系型微信助手设计</a> ——
          从「关系化」出发的产品与工程设计。
        </li>
      </ul>
      <p>
        这份 README 是入口，三份文档是纵深。读完本文你已经掌握了它的定位、安全边界与
        上手路径；下一步无论是评估、部署还是参与开发，都能从上面三份文档继续。
      </p>
    </Section>
  );
}
