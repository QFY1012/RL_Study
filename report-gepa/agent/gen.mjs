// Run a pi agent in a workspace: write a report page, fix one, or check one.
//
//   LLM_API_KEY=... LLM_BASE_URL=... node agent/gen.mjs <workspace> <system.md> <model> [effort] [task.txt] [output]
//
// <workspace>/data/ holds the report's files. The guide is the system prompt; the
// user message only says where the data is and where the page goes, so the data
// reaches the model only through the read and bash tools. A task file replaces
// that message (repair.py uses it to fix a page in place, factcheck.py to check
// one). The agent writes <workspace>/<output>, index.html unless given, and is
// asked once more if it has not. read / write / edit are limited to the workspace and
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

const TASK = `工作目录下的 data/ 里是一份报告的数据(有 README 的话是数据说明)。先读懂数据，再按系统提示词的要求把它做成一个网页，写到工作目录的 index.html。
index.html 是一个完整的 HTML 文件,CSS 和脚本都写在里面，不引用任何外部资源(打开页面时没有网络)。
想看页面的效果，运行 pageshot index.html:它像读者一样滚动页面，每屏截一张图到 _shots/frames/,再给一张缩小的整页图 _shots/thumb.jpg,用 read 工具看这些图。改页面用 edit 工具直接改 index.html。写完就结束。`
const [wsArg, guidePath, modelId, effort = "high", taskPath, output = "index.html"] = process.argv.slice(2)
const NUDGE = `工作目录里还没有 ${output}。请把结果写到 ${output}。`
if (!wsArg || !guidePath || !modelId) {
  console.error("usage: node agent/gen.mjs <workspace> <system.md> <model> [effort] [task.txt] [output]")
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
const streamFn = session.agent.streamFn
session.agent.streamFn = (m, context, options) => streamFn(m, context, { ...options, maxTokens: MAX_TOKENS })

const name = path.basename(ws)
const t0 = Date.now()
let tools = 0
session.subscribe((e) => {
  if (e.type === "tool_execution_start") {
    tools += 1
    console.log(`${name}: ${e.toolName} ${String(e.args?.path ?? e.args?.command ?? "").replace(/\s+/g, " ").slice(0, 100)}`)
  } else if (e.type === "message_end" && e.message.role === "assistant" && e.message.errorMessage) {
    console.log(`${name}: error ${e.message.errorMessage.slice(0, 200)}`)
  }
})
await session.prompt(taskPath ? fs.readFileSync(taskPath, "utf8") : TASK)
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
