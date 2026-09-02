import { Section } from "reacticle";

// 第六节：本地演示与模型回退 —— source.md「新版能力」第 5、6 条。
// 正文为主体：演示模式离线体验 + Ollama/OpenAI 回退 + 本地缓存与待确认队列持续读本地状态。
export function SectionLocalDemo() {
  return (
    <Section index="06" title="本地演示与模型回退">
      <p>
        想先看它跑起来，不需要真实微信环境。<strong>演示模式可离线体验</strong>：粘贴一段虚构
        对话，就能走完「生成草稿 → 待确认 → 人工确认」的完整流程，模型能力也支持
        <strong>Ollama 和 OpenAI 兼容接口</strong>——选本地模型还是外部接口，由你决定。
      </p>
      <p>
        外部调用不是单点依赖：<strong>外部调用失败时回退到本地模板</strong>。即使某个接口临时
        不可用，工作台仍然能基于本地模板产出草稿，不会因为上游故障而完全停摆。
      </p>
      <p>
        最后是两项「更顺畅的本地体验」细节：<strong>公开启动资料会短时缓存在浏览器本地</strong>，
        减少重复加载；同时<strong>待确认队列仍持续读取本地状态</strong>——你在确认时看到的是
        最新会话信息，避免用过期信息去确认发送。缓存只在浏览器本地、只用于提速，不改变
        「数据默认留在本机」的边界。
      </p>
    </Section>
  );
}
