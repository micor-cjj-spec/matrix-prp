import { defineConfig, loadEnv } from 'vite'
import uniPlugin from '@dcloudio/vite-plugin-uni'

type UniPluginFactory = () => ReturnType<typeof uniPlugin>
const candidate = uniPlugin as unknown as UniPluginFactory | { default: UniPluginFactory }
const uni = typeof candidate === 'function' ? candidate : candidate.default

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8080'

  return {
    plugins: [uni()],
    server: {
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
