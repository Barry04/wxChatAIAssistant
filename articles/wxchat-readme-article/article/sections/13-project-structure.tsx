import { Section, CodeBlock } from "reacticle";

// 第十三节：项目结构 —— source.md「项目结构」目录树（8 个目录，100% 保留）。
export function SectionProjectStructure() {
  return (
    <Section index="13" title="项目结构">
      <p>代码按职责分成清晰的目录，一眼能看出「谁管生成、谁管发送、谁管数据」：</p>
      <CodeBlock
        language="text"
        title="目录树"
        code={`app/agent/              LangGraph 草稿生成图
app/runtime/            Watcher、PolicyGate 与自动化编排
app/operator/           受控微信发送与发送后验证
frontend/               React + Vite 工作台
skills/relationships/   关系类型沟通配置
data/                   本地个人数据（不会上传）
tests/                  自动化测试
docs/                   架构、命令和设计文档`}
      />
      <p>
        注意三处和文章主线呼应的结构：<code>app/agent/</code> 对应多角色草稿生成，
        <code>app/operator/</code> 对应受控发送，<code>data/</code> 对应本地数据——
        生成、发送、数据三件事在代码层面就是分开的，不是靠约定、而是靠结构。
      </p>
    </Section>
  );
}
