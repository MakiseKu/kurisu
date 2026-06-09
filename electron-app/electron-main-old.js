const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')

// ── 开发模式热重载 ────────────────────────────────────────────────────
if (!app.isPackaged) {
  try {
    require('electron-reloader')(module, {
      debug: false,
      watchRenderer: false,
      ignore: [
        /node_modules/,
        /venv/,
        /\.pyc$/,
        /__pycache__/,
        /logs/,
        /data/,
        /chroma/,
      ],
    })
    console.log('[Dev] electron-reloader 已启动 ✓')
  } catch (e) {
    console.warn('[Dev] electron-reloader 加载失败:', e.message)
  }

  const uiDir = path.join(__dirname, '..', 'ui')
  let reloadTimer = null

  fs.watch(uiDir, { recursive: true }, (eventType, filename) => {
    if (!filename) return
    clearTimeout(reloadTimer)
    reloadTimer = setTimeout(() => {
      for (const win of BrowserWindow.getAllWindows()) {
        if (!win.isDestroyed()) {
          console.log(`[Dev] ui/ 已变更，刷新窗口 ✓`)
          win.webContents.reloadIgnoringCache()
        }
      }
    }, 100)
  })

  console.log('[Dev] fs.watch 已监听 ui/ 目录 ✓')
}

// ── 1. 启动 Python API 后端 ─────────────────────────────────────────
let pythonProcess = null

function startPythonBackend() {
  const kurisuDir = path.join(__dirname, '..')

  const venvPython = process.platform === 'win32'
    ? path.join(kurisuDir, 'venv', 'Scripts', 'python.exe')
    : path.join(kurisuDir, 'venv', 'bin', 'python')

  const systemPython = process.platform === 'win32' ? 'python' : 'python3'
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : systemPython

  console.log('[Electron] 使用 Python:', pythonCmd)

  let spawnArgs
  if (!app.isPackaged) {
    spawnArgs = [
      '-m', 'uvicorn',
      'api_server:app',
      '--host', '127.0.0.1',
      '--port', '8765',
      '--reload',
      '--reload-dir', kurisuDir,
      '--reload-exclude', 'venv',
      '--reload-exclude', 'data',
      '--reload-exclude', 'logs',
      '--reload-exclude', '__pycache__',
      '--log-level', 'info',
    ]
    console.log('[Dev] uvicorn --reload 模式 ✓')
  } else {
    spawnArgs = ['api_server.py']
  }

  pythonProcess = spawn(pythonCmd, spawnArgs, {
    cwd: kurisuDir,
    stdio: ['ignore', 'inherit', 'inherit'],
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
    },
  })

  pythonProcess.on('error', (err) => {
    console.error('[Electron] Python 启动失败:', err.message)
  })

  pythonProcess.on('exit', (code) => {
    console.log(`[Electron] Python 进程退出，code=${code}`)
  })

  console.log('[Electron] Python API 后端已启动 (pid=' + pythonProcess.pid + ')')
}

// ── 2. 等待后端就绪（轮询 /api/ping）─────────────────────────────────
function waitForBackend(maxRetries = 60, interval = 500) {
  return new Promise((resolve) => {
    let retries = 0
    const check = () => {
      const req = http.get('http://127.0.0.1:8765/api/ping', (res) => {
        if (res.statusCode === 200) {
          console.log('[Electron] 后端已就绪 ✓')
          resolve()
        } else {
          retry()
        }
        res.resume()
      })
      req.on('error', retry)
      req.setTimeout(400, () => { req.destroy(); retry() })

      function retry() {
        retries++
        if (retries >= maxRetries) {
          console.warn('[Electron] 后端未能在规定时间内就绪，仍继续加载前端')
          resolve()
        } else {
          setTimeout(check, interval)
        }
      }
    }
    check()
  })
}

// ── 3. 创建对话窗口（learn.html）─────────────────────────────────────
let mainWindow = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 420,
    height: 520,

    frame: true,
    transparent: false,
    alwaysOnTop: true,
    resizable: true,
    hasShadow: false,

    x: 1400,
    y: 200,

    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,
    }
  })

  const htmlPath = path.join(__dirname, '..', 'ui', 'learn.html')
  mainWindow.loadFile(htmlPath)

  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  }
}

// ── 3b. 创建桌宠形象窗口（pet.html）──────────────────────────────────
let petWindow = null

function createPetWindow() {
  petWindow = new BrowserWindow({
    width: 420,
    height: 520,

    // 无边框：去掉标题栏，拖拽由 pet.html CSS -webkit-app-region:drag 接管
    frame: false,

    /*
     * ★ transparent: true
     *
     * 让窗口的 OS 合成层透明，配合 pet.html 里的 CSS background:transparent
     * 才能实现真正的透明效果（两者缺一不可）。
     *
     * 对拖拽的影响：
     *   · -webkit-app-region:drag 在有可见像素的区域依然完全有效
     *   · 拖 GIF 图片 = 移动整个窗口，和有背景色时完全一样
     *   · 真正破坏拖拽的是 setIgnoreMouseEvents(true,{forward:true})
     *     本项目没有使用，所以拖拽完全正常
     *
     * ★ 关于 resizable 的重要说明（Windows 已知限制）：
     *   Windows 上，调整窗口大小依赖 WS_THICKFRAME 窗口样式，
     *   而 transparent:true 的窗口无法设置这个样式。
     *   因此在 Windows 上，transparent:true 时 resizable:true 实际无效——
     *   窗口边缘无法拖拽缩放，即使设置了 resizable:true 也没有效果。
     *   （Electron GitHub issue #6107，长期存在的 OS 层面限制）
     *   所以这里直接设为 false，避免产生"以为可以缩放但其实不行"的误导。
     */
    transparent: true,

    alwaysOnTop: true,
    resizable: false,   // Windows 上 transparent:true 时 resizable 无效，明确设 false
    hasShadow: false,

    x: 1400,
    y: 760,

    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,
    }
  })

  const petHtmlPath = path.join(__dirname, '..', 'ui', 'pet.html')
  petWindow.loadFile(petHtmlPath)

  if (!app.isPackaged) {
    petWindow.webContents.openDevTools({ mode: 'detach' })
  }
}

// ── 4. 应用生命周期 ───────────────────────────────────────────────────
app.whenReady().then(async () => {
  startPythonBackend()
  await waitForBackend()
  createWindow()
  createPetWindow()
})

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill()
    console.log('[Electron] Python 进程已关闭')
  }
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
