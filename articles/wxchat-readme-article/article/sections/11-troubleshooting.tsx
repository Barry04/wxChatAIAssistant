import { Section, CodeBlock } from "reacticle";

// 第十一节：日志与排查 —— source.md「日志与排查」整节。
// CodeBlock（2 条 PowerShell 命令）+ 2 个 API 端点 + 隐私承诺 + OCR 校验说明。
export function SectionTroubleshooting() {
  return (
    <Section index="11" title="日志与排查">
      <p>排查时先看两条实时日志（PowerShell）：</p>
      <CodeBlock
        language="powershell"
        title="实时日志"
        code={`Get-Content .\\data\\model-calls.jsonl -Tail 20 -Wait
Get-Content .\\data\\automation-events.jsonl -Tail 20 -Wait`}
      />
      <p>服务运行后，也可以通过 HTTP 接口查看：</p>
      <CodeBlock
        language="text"
        title="API 端点"
        code={`GET http://127.0.0.1:8787/api/logs/model-calls?limit=50
GET http://127.0.0.1:8787/api/automation/events?limit=50`}
      />
      <p>
        日志本身也是隐私边界的一部分：<strong>模型调用日志不会保存 API Key、提示词、聊天正文
        或模型回复</strong>——你能看到「调用过、结果如何」，但看不到不该留下的内容。
      </p>
      <p>
        针对真实发送还有一个专门的校验：Windows 微信 4.1 的发送会<strong>使用系统 OCR 校验
        右侧顶部会话标题</strong>，确认目标窗口没被切走；<strong>目标不一致时会中止</strong>，
        临时图像在识别后删除。这是「受控发送」在操作系统层面的最后一道保险。
      </p>
    </Section>
  );
}
