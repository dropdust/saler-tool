/**
 * 任务终态集合（任务契约 §1 与任务中心 store 共用）。
 *
 * `watchJob` 轮询已删除（T238~T241 存量调用点全部迁移）：等待任务一律经
 * `stores/jobCenter` 的 `waitFor`（唯一 SSE 订阅方，全应用一处状态）。
 */
export const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled', 'interrupted']
