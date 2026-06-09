const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  // 获取窗口当前位置（异步回调）
  getWindowPos: (callback) => {
    ipcRenderer.once('window-pos', (_e, x, y) => callback(x, y))
    ipcRenderer.send('get-window-pos')
  },
  // 设置窗口位置
  setWindowPos: (x, y) => {
    ipcRenderer.send('set-window-pos', x, y)
  }
})
