/**
 * preload-main.js — 主对话窗口（index.html）的 contextBridge 预加载脚本
 *
 * 暴露与桌宠联动相关的能力（如触发桌宠弹跳、切换状态等）。
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronMain', {
  // 通知桌宠切换状态（如：回复完成后让桌宠播放 talk 动画）
  setPetState: (state, opts) => {
    ipcRenderer.send('main-set-pet-state', { state, opts })
  },

  // 通知主进程 TTS 开关状态（可选）
  setTTS: (enabled) => {
    ipcRenderer.send('main-set-tts', { enabled })
  },
})
