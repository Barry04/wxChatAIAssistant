import { Section, CodeBlock } from "reacticle";

// 第八节：快速开始 —— source.md「快速开始」整节（含三段 CodeBlock，100% 保留命令原文）。
export function SectionQuickStart() {
  return (
    <Section index="08" title="快速开始">
      <p>
        上手需要 <strong>Windows、Python 3.10+ 和 Node.js</strong>。需要说明：微信本地读取与
        受控发送面向 <strong>Windows 微信环境</strong>——这是它「本地优先」承诺的载体。
      </p>

      <p>第一步，创建虚拟环境并安装后端依赖：</p>
      <CodeBlock
        language="powershell"
        title="后端依赖"
        code={`python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt`}
      />

      <p>第二步，构建前端并启动服务：</p>
      <CodeBlock
        language="powershell"
        title="启动服务"
        code={`Set-Location frontend
npm install
npm run build
Set-Location ..
.\\run.ps1`}
      />

      <p>
        第三步，打开 <a href="http://127.0.0.1:8787">http://127.0.0.1:8787</a> 使用工作台。
      </p>

      <p>开发前端时可改用热更新模式：</p>
      <CodeBlock
        language="powershell"
        title="开发模式"
        code={`Set-Location frontend
npm run dev`}
      />
    </Section>
  );
}
