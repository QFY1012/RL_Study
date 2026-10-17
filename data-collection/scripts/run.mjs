// Record, replay, generate, render and pair a list of sites, many at once.
//   node scripts/run.mjs <out-root> <url>...      (or a file of URLs, one per line, via --list <file>)
// Each site goes to <out-root>/<host>/ and its output to <out-root>/<host>.log; every
// line is also printed here, prefixed with the host. JOBS sites run at once (default
// 20); the browser steps (record, render, pairs) are CPU-bound, so at most
// BROWSER_JOBS of them run at a time (default 4) while the others wait on the model.
// A generated section that misses its height (fit.mjs) is sent back to the model and
// rendered again, up to ROUNDS times (default 2).
// Needs ~/.config/ui-rl/judge.env in the environment for generate.mjs.
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const args = process.argv.slice(2)
const root = args.shift()
if (!root) throw new Error("usage: run.mjs <out-root> <url>... | --list <file>")
const urls = args[0] === "--list" ? fs.readFileSync(args[1], "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#")) : args
const JOBS = Number(process.env.JOBS ?? 20)
const BROWSER_JOBS = Number(process.env.BROWSER_JOBS ?? 4)
const COUNT = process.env.COUNT ?? "2"
const ROUNDS = Number(process.env.ROUNDS ?? 2)
const misses = (dir) => {
  const r = path.join(dir, "render")
  return fs.existsSync(r) && fs.readdirSync(r).some((f) => /^\d+\.json$/.test(f) && !JSON.parse(fs.readFileSync(path.join(r, f), "utf8")).fits)
}
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
const browser = limiter(BROWSER_JOBS)

function step(host, log, cmd, argv, env = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, argv, { cwd: here, env: { ...process.env, ...env } })
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
      if (rest) console.log(`[${host}] ${rest}`)
      code === 0 ? resolve() : reject(new Error(`${path.basename(argv[0] ?? cmd)} exited with ${code}`))
    })
  })
}

async function site(url) {
  const host = new URL(url).hostname.replace(/^www\./, "")
  const dir = path.join(root, host)
  fs.rmSync(dir, { recursive: true, force: true })
  const log = fs.createWriteStream(`${dir}.log`)
  const t = Date.now()
  try {
    await browser(() => step(host, log, "node", ["scripts/record.mjs", url, dir]))
    await browser(() => step(host, log, "node", ["scripts/render.mjs", dir]))
    await step(host, log, "node", ["--no-warnings", "scripts/generate.mjs", dir, COUNT], { NODE_USE_ENV_PROXY: "1" })
    await browser(() => step(host, log, "node", ["scripts/render.mjs", dir]))
    // sections that missed their height go back to the model, up to ROUNDS times
    for (let k = 0; k < ROUNDS && misses(dir); k++) {
      await step(host, log, "node", ["--no-warnings", "scripts/generate.mjs", dir, "--revise"], { NODE_USE_ENV_PROXY: "1" })
      await browser(() => step(host, log, "node", ["scripts/render.mjs", dir]))
    }
    await browser(() => step(host, log, "python3", ["-I", "scripts/pairs.py", dir]))
    console.log(`[${host}] done in ${((Date.now() - t) / 1000).toFixed(0)}s`)
    return { host, ok: true }
  } catch (e) {
    console.log(`[${host}] FAILED: ${e.message}`)
    return { host, ok: false, error: e.message }
  } finally {
    log.end()
  }
}

const sites = limiter(JOBS)
const t = Date.now()
const results = await Promise.all(urls.map((u) => sites(() => site(u))))
const failed = results.filter((r) => !r.ok)
console.log(`${results.length - failed.length}/${results.length} sites done in ${((Date.now() - t) / 1000).toFixed(0)}s${failed.length ? `; failed: ${failed.map((f) => `${f.host} (${f.error})`).join(", ")}` : ""}`)
