# Matrix PRP Web

Vue 3 + TypeScript web console for Matrix PRP.

## Scripts

```bash
npm install
npm run dev
npm run build
```

The dev server proxies `/api` to `http://localhost:8080`.

Override the backend target with a local `.env` file when needed:

```bash
VITE_API_PROXY_TARGET=http://localhost:8080
```
