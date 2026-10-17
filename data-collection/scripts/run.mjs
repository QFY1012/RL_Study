// Record, replay, generate, render and pair a list of sites, many at once.
//   node scripts/run.mjs <out-root> <url>...      (or a file of URLs, one per line, via --list <file>)
// Each site goes to <out-root>/<host>/ and its output to <out-root>/<host>.log; every
// line is also printed here, prefixed with the host. JOBS sites run at once (default
// 20); the browser steps (record, render, pairs) are CPU-bound, so at most
// BROWSER_JOBS of them run at a time (default 2: with no GPU a heavy page takes about
// two of the four cores) while the others wait on the model.
// After each render pairs.py checks the pairs; a generated section that does not fit
// its box or shows a seam at its edge is sent back to the model and rendered again, up
// to ROUNDS times (default 2).
// A browser step that takes longer than STEP_SECONDS (default 300) is stopped and the
// site counted as failed: some pages (a large WebGL scene drawn on the CPU, with no
// GPU here) are too heavy to load, and they are dropped rather than waited on.
// Needs ~/.config/ui-rl/judge.env in the environment for generate.mjs.
import fs from "node:fs"
import path from "node:path"
import { spawn } from "node:child_process"

const args = process.argv.slice(2)
const root = args.shift()
if (!root) throw new Error("usage: run.mjs <out-root> <url>... | --list <file>")
const urls = args[0] === "--list" ? fs.readFileSync(args[1], "utf8").split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("#")) : args
const JOBS = Number(process.env.JOBS ?? 20)
const BROWSER_JOBS = Number(process.env.BROWSER_JOBS ?? 2)
const COUNT = process.env.COUNT ?? "2"
const ROUNDS = Number(process.env.ROUNDS ?? 2)
const STEP_SECONDS = Number(process.env.STEP_SECONDS ?? 300)
const misses = (dir) => Object.values(JSON.parse(fs.readFileSync(path.join(dir, "pairs", "report.json"), "utf8")).pairs).some((p) => p.failed.includes("fit") || p.failed.includes("seam"))
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

function step(host, log, cmd, argv, env = {}, seconds = Infinity) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, argv, { cwd: here, env: { ...process.env, ...env } })
    let late = false
    const timer = seconds < Infinity && setTimeout(() => { late = true; child.kill("SIGTERM") }, seconds * 1000)
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
      clearTimeout(timer)
      if (rest) console.log(`[${host}] ${rest}`)
      const name = path.basename(argv.find((a) => a.startsWith("scripts/")) ?? cmd)
      late ? reject(new Error(`${name} took over ${seconds}s`))
        : code === 0 ? resolve() : reject(new Error(`${name} exited with ${code}`))
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
    await browser(() => step(host, log, "node", ["scripts/record.mjs", url, dir], {}, STEP_SECONDS))
    await browser(() => step(host, log, "node", ["scripts/render.mjs", dir], {}, STEP_SECONDS))
    await step(host, log, "node", ["--no-warnings", "scripts/generate.mjs", dir, COUNT], { NODE_USE_ENV_PROXY: "1" })
    await browser(() => step(host, log, "node", ["scripts/render.mjs", dir], {}, STEP_SECONDS))
    await browser(() => step(host, log, "python3", ["-I", "scripts/pairs.py", dir], {}, STEP_SECONDS))
    // sections that do not fit their box or show a seam go back to the model, up to ROUNDS times
    for (let k = 0; k < ROUNDS && misses(dir); k++) {
      await step(host, log, "node", ["--no-warnings", "scripts/generate.mjs", dir, "--revise"], { NODE_USE_ENV_PROXY: "1" })
      await browser(() => step(host, log, "node", ["scripts/render.mjs", dir], {}, STEP_SECONDS))
      await browser(() => step(host, log, "python3", ["-I", "scripts/pairs.py", dir], {}, STEP_SECONDS))
    }
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
