import { Section, CodeBlock } from "reacticle";

// 第十二节：检查 —— source.md「检查」整节（4 条命令，100% 保留）。
export function SectionChecks() {
  return (
    <Section index="12" title="检查">
      <p>提交或发布前，跑一遍完整的检查链路：</p>
      <CodeBlock
        language="powershell"
        title="检查命令"
        code={`.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m compileall -q app
Set-Location frontend
npm run lint
npm run build`}
      />
      <p>
        四步各管一件事：<strong>pytest</strong> 跑自动化测试，<strong>compileall</strong> 校验
        后端代码可编译，<strong>lint</strong> 检查前端代码规范，<strong>build</strong> 确认前端
        能完整构建。命令覆盖了后端、前端与测试三个面——对一个同时涉及微信读取、Agent 编排
        和受控发送的工具来说，这套检查是「改动不破坏既有保障」的最低门槛。
      </p>
    </Section>
  );
}
