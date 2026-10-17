// Runs site.mjs for a list of sites as a pipeline.
//   node scripts/run.mjs <out-root> <url>...      (or a file of URLs, one per line, via --list <file>)
// Each site goes to <out-root>/<host>/ and its output to <out-root>/<host>.log; every
// line is also printed here, prefixed with the host. A site goes through two stages:
// loading its page, which takes the CPU (with no GPU a heavy page takes about two of
// the four cores), then the model and the swaps, which take minutes of waiting on the
// model and next to no CPU (the page's scripts are off). So the two run as a pipeline:
// BROWSER_JOBS sites load at a time (default 2), and as soon as one is loaded the next
// starts loading, however many are waiting on the model. What bounds the sites in
// flight is memory (each holds a browser with its page, about 1GB): a site starts
// loading only while more than MEM_RESERVE_MB (default 3000) is available.
// Needs ~/.config/ui-rl/judge.env in the environment for the model.
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const args = process.argv.slice(2)
const root = args.shift()
if (!root) throw new Error("usage: run.mjs <out-root> <url>... | --list <file>")
const urls = args[0] === "--list" ? fs.readFileSync(args[1], "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#")) : args
const BROWSER_JOBS = Number(process.env.BROWSER_JOBS ?? 2)
const MEM_RESERVE_MB = Number(process.env.MEM_RESERVE_MB ?? 3000)
const here = path.dirname(import.meta.dirname)
fs.mkdirSync(root, { recursive: true })

const available = () => Number(/MemAvailable:\s+(\d+)/.exec(fs.readFileSync("/proc/meminfo", "utf8"))[1]) / 1024
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// One site; loaded() is called once its page is loaded (site.mjs says "loaded") or it
// ends, whichever comes first.
function site(url, loaded) {
  const host = new URL(url).hostname.replace(/^www\./, "")
  const dir = path.join(root, host)
  fs.rmSync(dir, { recursive: true, force: true })
  const log = fs.createWriteStream(`${dir}.log`)
  const t = Date.now()
  return new Promise((resolve) => {
    const child = spawn("node", ["--no-warnings", "scripts/site.mjs", url, dir], { cwd: here, env: { ...process.env, NODE_USE_ENV_PROXY: "1" }, stdio: ["ignore", "pipe", "pipe", "ipc"] })
    let done = false
    const once = () => { if (!done) { done = true; loaded() } }
    child.on("message", (m) => { if (m === "loaded") once() })
    let rest = ""
    const out = (chunk) => {
      log.write(chunk)
      const lines = (rest + chunk).split("\n")
      rest = lines.pop()
      for (const l of lines) console.log(`[${host}] ${l}`)
    }
    child.stdout.on("data", out)
    child.stderr.on("data", out)
    child.on("close", (code) => {
      once()
      if (rest) console.log(`[${host}] ${rest}`)
      log.end()
      const seconds = ((Date.now() - t) / 1000).toFixed(0)
      console.log(`[${host}] ${code === 0 ? `done in ${seconds}s` : `FAILED: exited with ${code} after ${seconds}s`}`)
      resolve({ host, ok: code === 0 })
    })
  })
}

const t = Date.now()
const running = []
let loadingNow = 0
for (const url of urls) {
  let said = false
  while (loadingNow >= BROWSER_JOBS || available() < MEM_RESERVE_MB) {
    if (loadingNow < BROWSER_JOBS && !said) { console.log(`waiting for memory: ${available().toFixed(0)}MB available, ${running.length} sites started, next ${url}`); said = true }
    await sleep(1000)
  }
  loadingNow++
  running.push(site(url, () => loadingNow--))
}
const results = await Promise.all(running)
const failed = results.filter((r) => !r.ok)
console.log(`${results.length - failed.length}/${results.length} sites done in ${((Date.now() - t) / 1000).toFixed(0)}s${failed.length ? `; failed: ${failed.map((f) => f.host).join(", ")}` : ""}`)
