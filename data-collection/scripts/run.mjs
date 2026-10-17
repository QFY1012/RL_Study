// Runs site.mjs for a list of sites, many at once.
//   node scripts/run.mjs <out-root> <url>...      (or a file of URLs, one per line, via --list <file>)
// Each site goes to <out-root>/<host>/ and its output to <out-root>/<host>.log; every
// line is also printed here, prefixed with the host. JOBS sites run at once (default
// 20; each holds a browser with its page, about half a GB). Loading a page is what
// takes the CPU (with no GPU a heavy page takes about two of the four cores), so at
// most BROWSER_JOBS sites load at a time (default 2); the others wait on the model,
// with their pages' scripts off, costing next to nothing.
// Needs ~/.config/ui-rl/judge.env in the environment for the model.
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const args = process.argv.slice(2)
const root = args.shift()
if (!root) throw new Error("usage: run.mjs <out-root> <url>... | --list <file>")
const urls = args[0] === "--list" ? fs.readFileSync(args[1], "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#")) : args
const JOBS = Number(process.env.JOBS ?? 20)
const BROWSER_JOBS = Number(process.env.BROWSER_JOBS ?? 2)
const here = path.dirname(import.meta.dirname)
fs.mkdirSync(root, { recursive: true })

function limiter(n) {
  let active = 0
  const queue = []
  const next = () => { if (active < n && queue.length) { active++; queue.shift()() } }
  return (fn) => new Promise((resolve, reject) => {
    queue.push(() => fn().then(resolve, reject).finally(() => { active--; next() }))
    next()
  })
}
const cpu = limiter(BROWSER_JOBS)

function site(url) {
  const host = new URL(url).hostname.replace(/^www\./, "")
  const dir = path.join(root, host)
  fs.rmSync(dir, { recursive: true, force: true })
  const log = fs.createWriteStream(`${dir}.log`)
  const t = Date.now()
  return new Promise((resolve) => {
    const child = spawn("node", ["--no-warnings", "scripts/site.mjs", url, dir], { cwd: here, env: { ...process.env, NODE_USE_ENV_PROXY: "1" }, stdio: ["ignore", "pipe", "pipe", "ipc"] })
    // site.mjs asks for a turn at the CPU ("take") and gives it back ("give"); a site
    // that ends while it has it or waits for it gives it back too
    let give = null, closed = false
    child.on("message", (m) => {
      if (m === "take") cpu(() => new Promise((r) => { if (closed) return r(); give = r; child.send("go") }))
      if (m === "give") give?.()
    })
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
      closed = true
      give?.()
      if (rest) console.log(`[${host}] ${rest}`)
      log.end()
      const seconds = ((Date.now() - t) / 1000).toFixed(0)
      console.log(`[${host}] ${code === 0 ? `done in ${seconds}s` : `FAILED: exited with ${code} after ${seconds}s`}`)
      resolve({ host, ok: code === 0 })
    })
  })
}

const sites = limiter(JOBS)
const t = Date.now()
const results = await Promise.all(urls.map((u) => sites(() => site(u))))
const failed = results.filter((r) => !r.ok)
console.log(`${results.length - failed.length}/${results.length} sites done in ${((Date.now() - t) / 1000).toFixed(0)}s${failed.length ? `; failed: ${failed.map((f) => f.host).join(", ")}` : ""}`)
