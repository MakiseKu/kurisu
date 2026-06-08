const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')

// ── 开发模式热重载 ────────────────────────────────────────────────────
// electron-reloader 负责监听 electron-main.js 自身变化 → 自动重启 Electron
// fs.watch 负责监听 ui/ 目录变化 → 自动刷新渲染窗口（reloader 够不到 ui/）
if (!app.isPackaged) {
  // ① 主进程文件热重载（electron-main.js 本身改变时重启整个 Electron）
  try {
    require('electron-reloader')(module, {
      debug: false,
      watchRenderer: false,   // 关掉 reloader 的渲染层监听，由下面 fs.watch 接管
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
    console.log('[Dev] electron-reloader 已启动 ── 修改 electron-main.js 保存即重启 ✓')
  } catch (e) {
    console.warn('[Dev] electron-reloader 加载失败:', e.message)
  }

  // ② ui/ 目录热重载（index.html / CSS / JS 改变时刷新渲染窗口）
  //    用 fs.watch recursive 监听整个 ui/ 目录，有任何文件变化就 reload
  const uiDir = path.join(__dirname, '..', 'ui')
  let reloadTimer = null   // 防抖：100ms 内多个文件同时变化只触发一次刷新

  fs.watch(uiDir, { recursive: true }, (eventType, filename) => {
    if (!filename) return
    clearTimeout(reloadTimer)
    reloadTimer = setTimeout(() => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        console.log(`[Dev] ui/${filename} 已变更，刷新窗口 ✓`)
        mainWindow.webContents.reloadIgnoringCache()
      }
    }, 100)
  })

  console.log('[Dev] fs.watch 已监听 ui/ 目录 ── 修改 index.html 保存即刷新 ✓')
}

// ── 1. 启动 Python API 后端 ─────────────────────────────────────────
let pythonProcess = null

function startPythonBackend() {
  const kurisuDir = path.join(__dirname, '..')

  // 优先使用 venv 里的 Python（依赖都装在 venv 里）
  const venvPython = process.platform === 'win32'
    ? path.join(kurisuDir, 'venv', 'Scripts', 'python.exe')
    : path.join(kurisuDir, 'venv', 'bin', 'python')

  const systemPython = process.platform === 'win32' ? 'python' : 'python3'
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : systemPython

  console.log('[Electron] 使用 Python:', pythonCmd)

  // 开发模式：uvicorn --reload，改完 .py 自动重启后端
  // 生产模式：直接 python api_server.py，稳定优先
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
    console.log('[Dev] uvicorn --reload 模式 ── 修改 .py 保存即自动重启后端 ✓')
  } else {
    spawnArgs = ['api_server.py']
  }

  pythonProcess = spawn(pythonCmd, spawnArgs, {
    cwd: kurisuDir,
    stdio: ['ignore', 'inherit', 'inherit'],
    // ★ 修复 Windows GBK 编码：强制 Python 子进程使用 UTF-8 I/O
    // 不加这两个变量，Python 继承终端的 GBK 编码，✓等 Unicode 字符会让进程崩溃
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',   // Python 3.6+ 标准变量，强制 stdin/stdout/stderr 用 UTF-8
      PYTHONUTF8: '1',             // Python 3.7+ 的 UTF-8 模式，更彻底（相当于 -X utf8 参数）
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
          console.warn('[Electron] 后端未能在规定时间内就绪（RAG 初始化较慢），仍继续加载前端')
          resolve()
        } else {
          setTimeout(check, interval)
        }
      }
    }
    check()
  })
}

// ── 3. 创建窗口 ───────────────────────────────────────────────────────
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

// ── 4. 应用生命周期 ───────────────────────────────────────────────────
app.whenReady().then(async () => {
  startPythonBackend()
  await waitForBackend()
  createWindow()
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
