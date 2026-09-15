import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, relative } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const src = join(root, 'src')
const temp = mkdtempSync(join(tmpdir(), 'ncs-syntax-'))
const failures = []
let checked = 0

function walk(dir) {
  const result = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) result.push(...walk(path))
    else result.push(path)
  }
  return result
}

function checkFile(label, source) {
  const path = join(temp, `check-${checked}.mjs`)
  writeFileSync(path, source)
  const result = spawnSync(process.execPath, ['--check', path], { encoding: 'utf8' })
  checked += 1
  if (result.status !== 0) failures.push(`${label}: ${result.stderr.trim()}`)
}

for (const file of walk(src)) {
  if (file.endsWith('.js')) checkFile(relative(root, file), readFileSync(file, 'utf8'))
  if (file.endsWith('.vue')) {
    const text = readFileSync(file, 'utf8')
    const match = text.match(/<script\s+setup[^>]*>([\s\S]*?)<\/script>/)
    if (match) checkFile(`${relative(root, file)} <script setup>`, match[1])
  }
}
for (const file of walk(join(root, 'scripts'))) {
  if (file.endsWith('.mjs') && !file.endsWith('check-syntax.mjs')) checkFile(relative(root, file), readFileSync(file, 'utf8'))
}

rmSync(temp, { recursive: true, force: true })
if (failures.length) {
  console.error(`Syntax verification FAILED (${failures.length}/${checked})`)
  for (const failure of failures) console.error(failure)
  process.exit(1)
}
console.log(`Syntax verification PASSED (${checked} scripts checked)`)
