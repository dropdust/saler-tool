import { defineStore } from 'pinia'
import { api } from '../api/client'

export const useAppStore = defineStore('app', {
  state: () => ({
    settings: {} as Record<string, unknown>,
    health: null as { ok: boolean; version: string } | null,
  }),
  actions: {
    async loadHealth() {
      try {
        this.health = await api.get<{ ok: boolean; version: string }>('/health')
      } catch {
        this.health = null
      }
    },
    async loadSettings() {
      this.settings = await api.get<Record<string, unknown>>('/settings')
    },
    async saveSettings(values: Record<string, unknown>) {
      this.settings = await api.put<Record<string, unknown>>('/settings', { values })
    },
  },
})
