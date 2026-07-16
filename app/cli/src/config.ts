import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'

export interface CliConfig {
  apiBaseUrl: string
  token?: string
  username?: string
}

const defaultConfig: CliConfig = {
  apiBaseUrl: process.env.MATRIX_PRP_API_BASE_URL ?? 'http://localhost:8080/api',
}

const configRoot = process.env.MATRIX_PRP_CONFIG_DIR ?? join(homedir(), '.matrix-prp')
const configPath = join(configRoot, 'cli-config.json')

export async function loadConfig(): Promise<CliConfig> {
  try {
    const raw = await readFile(configPath, 'utf8')
    return { ...defaultConfig, ...JSON.parse(raw) }
  } catch {
    return { ...defaultConfig }
  }
}

export async function saveConfig(config: CliConfig) {
  await mkdir(dirname(configPath), { recursive: true })
  await writeFile(configPath, JSON.stringify(config, null, 2), 'utf8')
}

export function getConfigPath() {
  return configPath
}
