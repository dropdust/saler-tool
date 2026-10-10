# Saler 前端（Vue 3 + TypeScript）

Node ≥ 20 + pnpm。命令均在 `frontend/` 目录下执行。

## 安装与运行

```bash
pnpm install
pnpm dev      # 开发服务器 http://localhost:5173（/api 代理到本地后端 8620）
pnpm build    # 产出 dist/（随桌面包内嵌）
pnpm test     # vitest
pnpm lint     # eslint
```

## 约定

- 只依赖 `specs/001-sales-tool/contracts/local-api.md` 的本地 API；不内嵌业务规则。
- 鉴权：桌面壳通过 `?token=` 注入一次性令牌，`api/client.ts` 统一携带（SSE 用查询参数）。
- 界面中文优先（`i18n/zh-CN.ts`）。
