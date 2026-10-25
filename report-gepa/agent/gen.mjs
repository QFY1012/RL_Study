// Run a pi agent in a workspace: write a report page, fix one, or check one.
//
//   LLM_API_KEY=... LLM_BASE_URL=... node agent/gen.mjs <workspace> <system.md> <model> <effort> <task.md> [output]
//
// <workspace>/data/ holds the report's files. The guide is the system prompt and
// the task file is the user message (generate.py: the benchmark task plus how to
// use pageshot; repair.py: fix a page in place), so the data reaches the model
// only through the read and bash tools. The agent writes <workspace>/<output>,
// index.html unless given, and is asked once more if it has not. read / write / edit are limited to the workspace and
// bash runs in sandbox.sh. Prints one line per tool call, then one JSON line
// starting with "RESULT " that generate.py parses.
import fs from "node:fs"
import path from "node:path"
import { getModel } from "@mariozechner/pi-ai"
import {
  AuthStorage, createAgentSession, createExtensionRuntime, ModelRegistry, SessionManager, SettingsManager,
  createBashToolDefinition, createEditToolDefinition, createReadToolDefinition, createWriteToolDefinition,
} from "@mariozechner/pi-coding-agent"

const SANDBOX = path.join(import.meta.dirname, "sandbox.sh")
// pi asks for at most 32000 output tokens per step by default; a Pudding-style
// page took 47k including reasoning.
const MAX_TOKENS = 65536
// Steps (assistant turns) before the agent is told to stop polishing, and before it is cut off. Every step re-sends
// the whole context, so a runaway session costs many pages: 111 GEPA pages took 49 steps at the median and 123 at
// most, then one infinite page went past 300 (2026-10-22).
const WRAP_UP_STEPS = 150
const MAX_STEPS = 170
const WRAP_UP = `已经用了 ${WRAP_UP_STEPS} 步，到上限了。不要再截图检查或继续打磨，确认结果已经写好就结束。`

const [wsArg, guidePath, modelId, effort, taskPath, output = "index.html"] = process.argv.slice(2)
const NUDGE = `工作目录里还没有 ${output}。请把结果写到 ${output}。`
if (!wsArg || !guidePath || !modelId || !effort || !taskPath) {
  console.error("usage: node agent/gen.mjs <workspace> <system.md> <model> <effort> <task.md> [output]")
  process.exit(2)
}
const { LLM_API_KEY: KEY, LLM_BASE_URL: BASE } = process.env
if (!KEY || !BASE) throw new Error("set LLM_API_KEY and LLM_BASE_URL")
const ws = path.resolve(wsArg)
const system = fs.readFileSync(guidePath, "utf8")

// Both models go through the same OpenAI-compatible endpoint, described with pi's
// deepseek entry; reasoning effort is sent as reasoning_effort.
const base = getModel("deepseek", "deepseek-v4-flash")
const model = { ...base, id: modelId, baseUrl: BASE, input: ["text", "image"], maxTokens: MAX_TOKENS, compat: { ...base.compat, thinkingFormat: "openai" } }

const inside = (p) => {
  const abs = path.resolve(ws, p ?? "")
  return abs === ws || abs.startsWith(ws + path.sep)
}
const fence = (def) => ({
  ...def,
  execute: (id, params, ...rest) => (inside(params.path) ? def.execute(id, params, ...rest) : Promise.reject(new Error("只能访问工作目录内的文件"))),
})
const q = (x) => `'${x.replace(/'/g, `'\\''`)}'`
const bash = createBashToolDefinition(ws, {
  spawnHook: ({ command }) => ({ command: `${q(SANDBOX)} ${q(ws)} ${q(command)}`, cwd: ws, env: { PATH: process.env.PATH } }),
})

// pi's own files (session, credentials) stay outside the workspace the agent can read.
const priv = fs.mkdtempSync(path.join(path.dirname(ws), `.${path.basename(ws)}-pi-`))
const auth = AuthStorage.create(path.join(priv, "auth.json"))
auth.setRuntimeApiKey("deepseek", KEY)
const loader = {
  getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
  getSkills: () => ({ skills: [], diagnostics: [] }),
  getPrompts: () => ({ prompts: [], diagnostics: [] }),
  getThemes: () => ({ themes: [], diagnostics: [] }),
  getAgentsFiles: () => ({ agentsFiles: [] }),
  getSystemPrompt: () => system,
  getAppendSystemPrompt: () => [],
  extendResources: () => {},
  reload: async () => {},
}
const { session } = await createAgentSession({
  cwd: ws,
  agentDir: path.join(priv, "pi"),
  model,
  thinkingLevel: effort,
  authStorage: auth,
  modelRegistry: ModelRegistry.inMemory(auth),
  resourceLoader: loader,
  noTools: "builtin",
  customTools: [fence(createReadToolDefinition(ws)), fence(createWriteToolDefinition(ws)), fence(createEditToolDefinition(ws)), bash],
  sessionManager: SessionManager.create(ws, priv),
  // A request that gets no response within 5 min is retried; a long streamed reply is not cut.
  // 30 s was too short once a session held a few dozen screenshots: the relay took longer than that to start
  // answering, so every turn timed out and re-sent the whole context (cetaceans, 2026-10-22).
  settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: true, maxRetries: 3, provider: { timeoutMs: 300_000 } } }),
})
// Images the agent read before its latest pageshot show an older version of the page, and every image kept in the
// context is processed again on every later step, uncached: about 0.85 s per image per step, as much as 10k tokens of
// text, so a page whose context held 20-26 screenshots spent 6-7 of its 17-22 minutes on them (pages4, 2026-10-25).
// They are left out of what the model is sent; the session file keeps them.
const STALE = { type: "text", text: "[screenshot of an earlier version of the page, left out]" }
const isPageshot = (m) => m.role === "assistant" && m.content.some((c) => c.type === "toolCall" && String(c.arguments?.command ?? "").includes("pageshot"))
const dropStaleShots = (messages) => {
  const last = messages.findLastIndex(isPageshot)
  return messages.map((m, i) =>
    i < last && m.role === "toolResult" && m.content.some((c) => c.type === "image")
      ? { ...m, content: m.content.map((c) => (c.type === "image" ? STALE : c)) }
      : m)
}
const streamFn = session.agent.streamFn
session.agent.streamFn = (m, context, options) =>
  streamFn(m, { ...context, messages: dropStaleShots(context.messages) }, { ...options, maxTokens: MAX_TOKENS })

const name = path.basename(ws)
const t0 = Date.now()
let tools = 0
let steps = 0
session.subscribe((e) => {
  if (e.type === "message_end" && e.message.role === "assistant") {
    steps += 1
    if (steps === WRAP_UP_STEPS) {
      console.log(`${name}: wrap up at ${steps} steps`)
      session.steer(WRAP_UP)
    } else if (steps === MAX_STEPS) {
      console.log(`${name}: stopped at ${steps} steps`)
      session.abort()
    }
  }
  if (e.type === "tool_execution_start") {
    tools += 1
    console.log(`${name}: ${e.toolName} ${String(e.args?.path ?? e.args?.command ?? "").replace(/\s+/g, " ").slice(0, 100)}`)
  } else if (e.type === "message_end" && e.message.role === "assistant" && e.message.errorMessage) {
    console.log(`${name}: error ${e.message.errorMessage.slice(0, 200)}`)
  }
})
await session.prompt(fs.readFileSync(taskPath, "utf8"))
let nudged = false
if (!fs.existsSync(path.join(ws, output))) {
  nudged = true
  console.log(`${name}: nudge`)
  await session.prompt(NUDGE)
}
const assistant = session.messages.filter((m) => m.role === "assistant")
const usage = assistant.reduce((u, m) => ({ input: u.input + (m.usage?.input ?? 0), output: u.output + (m.usage?.output ?? 0) }), { input: 0, output: 0 })
if (session.sessionFile && fs.existsSync(session.sessionFile)) fs.renameSync(session.sessionFile, path.join(ws, "session.jsonl"))
session.dispose()
fs.rmSync(priv, { recursive: true, force: true })
console.log("RESULT " + JSON.stringify({
  model: model.id, effort, seconds: Math.round((Date.now() - t0) / 1000), steps: assistant.length, tools, nudged, usage,
  stop: assistant.at(-1)?.stopReason ?? null, error: assistant.at(-1)?.errorMessage ?? null,
}))
