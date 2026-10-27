import hashlib
import json
import os
import shutil
import struct
import subprocess

ASAR_PATH = r"C:\Users\icand\AppData\Local\Programs\antigravity\resources\app.asar"
BACKUP_PATH = r"C:\Users\icand\AppData\Local\Programs\antigravity\resources\app.asar.bak"
PATCH_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\antigravity-korean-patch"
UI_KO_JSON_PATH = os.path.join(PATCH_DIR, "ui-ko.json")
I18N_KO_JS_PATH = os.path.join(PATCH_DIR, "i18n-ko.js")
VERIFY_DIR = os.path.join(PATCH_DIR, "verified_dist")


def compute_integrity(data_bytes):
    block_size = 4 * 1024 * 1024
    blocks = []
    if len(data_bytes) == 0:
        blocks.append(hashlib.sha256(b"").hexdigest())
    else:
        for i in range(0, len(data_bytes), block_size):
            blocks.append(hashlib.sha256(data_bytes[i : i + block_size]).hexdigest())
    return {
        "algorithm": "SHA256",
        "hash": hashlib.sha256(data_bytes).hexdigest(),
        "blockSize": block_size,
        "blocks": blocks,
    }


def read_asar(asar_file_path):
    with open(asar_file_path, "rb") as f:
        data = f.read()
    u0, u1, u2, u3 = struct.unpack("<IIII", data[:16])
    assert u0 == 4, f"Unexpected ASAR pickle u0={u0}"
    header_offset = 8 + u1
    header_json = data[16 : 16 + u3].decode("utf-8")
    header = json.loads(header_json)
    payload = data[header_offset:]
    return header, payload


def pack_asar(header, payload, out_path):
    header_str = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    u3 = len(header_str)
    # Pad to 4-byte boundary as required by Chromium Pickle
    pad_len = (4 - (u3 % 4)) % 4
    padded_header_str = header_str + (b"\x00" * pad_len)
    u2 = 4 + len(padded_header_str)
    u1 = 4 + u2
    u0 = 4
    prefix = struct.pack("<IIII", u0, u1, u2, u3)

    with open(out_path, "wb") as f:
        f.write(prefix)
        f.write(padded_header_str)
        f.write(payload)


def get_file_bytes(header, payload, rel_path):
    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    node = header
    for p in parts:
        node = node["files"][p]
    offset = int(node["offset"])
    size = int(node["size"])
    return payload[offset : offset + size]


def patch_files():
    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(ASAR_PATH, BACKUP_PATH)

    header, payload = read_asar(BACKUP_PATH)

    with open(UI_KO_JSON_PATH, "rb") as f:
        ui_ko_bytes = f.read()
    with open(I18N_KO_JS_PATH, "rb") as f:
        i18n_ko_bytes = f.read()

    # 1. Patch dist/preload.js
    preload_src = get_file_bytes(header, payload, "dist/preload.js").decode("utf-8")
    if "i18n-ko" not in preload_src:
        preload_src = preload_src.replace(
            "showContextMenu: (items) => electron_1.ipcRenderer.invoke('window:show-context-menu', items),",
            "showContextMenu: (items) => electron_1.ipcRenderer.invoke('window:show-context-menu', (typeof window !== 'undefined' && window.__agyTranslateMenuItemsKo) ? window.__agyTranslateMenuItemsKo(items) : items),",
        )
        preload_src += "\ntry { require('./i18n-ko'); } catch (e) { console.error('[i18n-ko preload]', e); }\n"

    # 2. Patch dist/utils.js
    utils_src = get_file_bytes(header, payload, "dist/utils.js").decode("utf-8")
    if "i18n-ko.js" not in utils_src:
        inject_snippet = """    const i18nScriptPath = path_1.default.join(__dirname, 'i18n-ko.js');
    const injectKoreanPatch = () => {
        try {
            if (fs.existsSync(i18nScriptPath)) {
                const scriptContent = fs.readFileSync(i18nScriptPath, 'utf-8');
                void win.webContents.executeJavaScript(scriptContent).catch(() => {});
            }
        } catch (err) {
            console.error('[i18n-ko] Failed to inject:', err);
        }
    };
    win.webContents.on('dom-ready', injectKoreanPatch);
    win.webContents.on('did-finish-load', injectKoreanPatch);
    void win.loadURL(url);"""
        utils_src = utils_src.replace("    void win.loadURL(url);", inject_snippet)

    # 3. Patch dist/ipcHandlers.js
    ipc_src = get_file_bytes(header, payload, "dist/ipcHandlers.js").decode("utf-8")
    if "translateMenuLabelKo" not in ipc_src:
        ko_helper = """const path_ko_1 = __importDefault(require("path"));
const fs_ko_1 = __importStar(require("fs"));
let _koDictCache = null;
function getKoDict() {
    if (_koDictCache) return _koDictCache;
    try {
        const raw = fs_ko_1.readFileSync(path_ko_1.default.join(__dirname, 'ui-ko.json'), 'utf-8');
        const parsed = JSON.parse(raw);
        const exact = parsed.exact || {};
        const norm = Object.create(null);
        for (const [k, v] of Object.entries(exact)) {
            norm[k] = v;
            norm[k.trim()] = v;
        }
        const patterns = (parsed.patterns || []).map(([p, r]) => [new RegExp(p), r.replace(/\\\\(\\d+)/g, '$$$1')]);
        _koDictCache = { exact, norm, patterns };
    } catch (e) {
        _koDictCache = { exact: {}, norm: {}, patterns: [] };
    }
    return _koDictCache;
}
function translateMenuLabelKo(label) {
    if (!label || typeof label !== 'string') return label ?? '';
    const { exact, norm, patterns } = getKoDict();
    if (exact[label] !== undefined) return exact[label];
    const trimmed = label.trim();
    if (norm[trimmed] !== undefined) return norm[trimmed];
    if (trimmed.startsWith('&') && norm[trimmed.slice(1)] !== undefined) {
        return norm[trimmed.slice(1)];
    }
    for (const [regex, repl] of patterns) {
        if (regex.test(trimmed)) return trimmed.replace(regex, repl);
    }
    return label;
}
function buildContextMenuTemplate(items, onSelect) {"""
        ipc_src = ipc_src.replace("function buildContextMenuTemplate(items, onSelect) {", ko_helper)
        ipc_src = ipc_src.replace("label: item.label ?? '',", "label: translateMenuLabelKo(item.label ?? ''),")
        ipc_src = ipc_src.replace("title: 'Open workspace',", "title: '워크스페이스 열기',")
        ipc_src = ipc_src.replace("title: 'Open workspaces',", "title: '워크스페이스 다중 열기',")
        ipc_src = ipc_src.replace("showErrorBox('Cannot open folder'", "showErrorBox('폴더를 열 수 없음'")
        ipc_src = ipc_src.replace("message: 'Folder is on the Windows filesystem',", "message: 'Windows 파일 시스템의 폴더입니다',")

    # 4. Patch dist/main.js
    main_src = get_file_bytes(header, payload, "dist/main.js").decode("utf-8")
    main_src = main_src.replace("label: 'New Window',", "label: '새 창',")
    main_src = main_src.replace("label: 'No agents running',", "label: '실행 중인 에이전트 없음',")
    main_src = main_src.replace("label: `Open ${electron_1.app.getName()}`,", "label: `${electron_1.app.getName()} 열기`,")
    main_src = main_src.replace("label: 'Quit',", "label: '종료',")
    main_src = main_src.replace("buttons: ['Cancel', 'Quit'],", "buttons: ['취소', '종료'],")
    main_src = main_src.replace("title: 'Confirm Quit',", "title: '종료 확인',")
    main_src = main_src.replace("message: 'Are you sure you want to quit?',", "message: '정말 종료하시겠습니까?',")
    main_src = main_src.replace(
        "detail: 'There may be agents or background tasks running.',",
        "detail: '실행 중인 에이전트나 백그라운드 작업이 있을 수 있습니다.',",
    )
    main_src = main_src.replace("title: 'WSL distro not found',", "title: 'WSL 배포판을 찾을 수 없음',")
    main_src = main_src.replace("detail: 'Antigravity opened on Windows instead.',", "detail: '대신 Windows 로컬 환경에서 Antigravity를 열었습니다.',")
    main_src = main_src.replace("showErrorBox('Binary not found'", "showErrorBox('실행 파일을 찾을 수 없음'")
    main_src = main_src.replace("showErrorBox('WSL setup failed'", "showErrorBox('WSL 설정 실패'")
    main_src = main_src.replace("showErrorBox('Startup failed'", "showErrorBox('시작 실패'")

    # 5. Patch dist/menu.js
    menu_src = get_file_bytes(header, payload, "dist/menu.js").decode("utf-8")
    menu_src = menu_src.replace("label: 'New Window',", "label: '새 창',")
    menu_src = menu_src.replace("label: 'Docs',", "label: '문서',")
    menu_src = menu_src.replace("label: 'Connect to WSL'", "label: 'WSL에 연결'")
    menu_src = menu_src.replace("label: 'Reopen Locally'", "label: '로컬에서 다시 열기'")

    # 6. Patch dist/tray.js
    tray_src = get_file_bytes(header, payload, "dist/tray.js").decode("utf-8")
    old_tray_count = """            countItem.label =
                (count > 0 ? `${count}` : 'No') +
                    ' agent' +
                    (count === 1 ? '' : 's') +
                    ' running';"""
    new_tray_count = """            countItem.label =
                count > 0 ? `에이전트 ${count}개 실행 중` : '실행 중인 에이전트 없음';"""
    tray_src = tray_src.replace(old_tray_count, new_tray_count)

    # 7. Patch dist/updater.js
    updater_src = get_file_bytes(header, payload, "dist/updater.js").decode("utf-8")
    updater_src = updater_src.replace('MenuUpdateStep["CheckForUpdates"] = "Check for Updates";', 'MenuUpdateStep["CheckForUpdates"] = "업데이트 확인";')
    updater_src = updater_src.replace('MenuUpdateStep["CheckingForUpdates"] = "Checking for Updates...";', 'MenuUpdateStep["CheckingForUpdates"] = "업데이트 확인 중...";')
    updater_src = updater_src.replace('MenuUpdateStep["DownloadingUpdate"] = "Downloading Update...";', 'MenuUpdateStep["DownloadingUpdate"] = "업데이트 다운로드 중...";')
    updater_src = updater_src.replace('MenuUpdateStep["RestartToUpdate"] = "Restart to Update";', 'MenuUpdateStep["RestartToUpdate"] = "재시작하여 업데이트";')
    updater_src = updater_src.replace("title: 'Check for Updates',", "title: '업데이트 확인',")
    updater_src = updater_src.replace("message: 'No updates available',", "message: '사용 가능한 업데이트가 없습니다',")
    updater_src = updater_src.replace("buttons: ['OK'],", "buttons: ['확인'],")

    # 8. Patch dist/provisionSplash.js
    splash_src = get_file_bytes(header, payload, "dist/provisionSplash.js").decode("utf-8")
    splash_src = splash_src.replace("<div>Setting up WSL: ${escapeHtml(distro)}</div>", "<div>WSL 설정 중: ${escapeHtml(distro)}</div>")

    # 9. Patch dist/ideInstall/wizardHtml.js
    wizard_src = get_file_bytes(header, payload, "dist/ideInstall/wizardHtml.js").decode("utf-8")
    wizard_src = wizard_src.replace("<title>Welcome to Antigravity</title>", "<title>Antigravity에 오신 것을 환영합니다</title>")
    wizard_src = wizard_src.replace(">Setting up…</div>", ">설정 중…</div>")
    wizard_src = wizard_src.replace("<h1>Welcome to the new Antigravity!</h1>", "<h1>새로운 Antigravity에 오신 것을 환영합니다!</h1>")
    wizard_src = wizard_src.replace(
        "<p>Antigravity has been redesigned to put agents first with new capabilities. If you'd still like a code editor, you can download it as a separate app named <b>Antigravity IDE</b>.</p>",
        "<p>Antigravity가 에이전트 중심의 새로운 기능으로 새롭게 단장되었습니다. 코드 편집기가 필요한 경우 별도 앱인 <b>Antigravity IDE</b>를 다운로드할 수 있습니다.</p>",
    )
    wizard_src = wizard_src.replace("<span>Download the Antigravity IDE</span>", "<span>Antigravity IDE 다운로드</span>")
    wizard_src = wizard_src.replace(">Explore the new Antigravity</button>", ">새로운 Antigravity 시작하기</button>")

    replacements = {
        "dist/preload.js": preload_src.encode("utf-8"),
        "dist/utils.js": utils_src.encode("utf-8"),
        "dist/ipcHandlers.js": ipc_src.encode("utf-8"),
        "dist/main.js": main_src.encode("utf-8"),
        "dist/menu.js": menu_src.encode("utf-8"),
        "dist/tray.js": tray_src.encode("utf-8"),
        "dist/updater.js": updater_src.encode("utf-8"),
        "dist/provisionSplash.js": splash_src.encode("utf-8"),
        "dist/ideInstall/wizardHtml.js": wizard_src.encode("utf-8"),
        "dist/ui-ko.json": ui_ko_bytes,
        "dist/i18n-ko.js": i18n_ko_bytes,
    }

    # Verify syntax of all modified JS files with `node --check`
    os.makedirs(os.path.join(VERIFY_DIR, "ideInstall"), exist_ok=True)
    for rel_path, content_bytes in replacements.items():
        out_verify = os.path.join(VERIFY_DIR, rel_path.replace("dist/", ""))
        os.makedirs(os.path.dirname(out_verify), exist_ok=True)
        with open(out_verify, "wb") as f:
            f.write(content_bytes)
        if rel_path.endswith(".js"):
            subprocess.run(["node", "--check", out_verify], check=True)

    # Ensure dist/ui-ko.json and dist/i18n-ko.js exist in header tree
    dist_files = header["files"]["dist"]["files"]
    dist_files["ui-ko.json"] = {"size": len(ui_ko_bytes), "offset": "0"}
    dist_files["i18n-ko.js"] = {"size": len(i18n_ko_bytes), "offset": "0"}

    # Rebuild payload preserving existing file order and appending replaced/new files cleanly
    new_payload = bytearray()

    def rebuild_tree(node, prefix=""):
        if "files" in node:
            for name, child in node["files"].items():
                child_path = f"{prefix}/{name}" if prefix else name
                rebuild_tree(child, child_path)
        else:
            if node.get("unpacked"):
                return
            if prefix in replacements:
                data_bytes = replacements[prefix]
            else:
                orig_off = int(node["offset"])
                orig_sz = int(node["size"])
                data_bytes = payload[orig_off : orig_off + orig_sz]
            new_off = len(new_payload)
            new_payload.extend(data_bytes)
            node["offset"] = str(new_off)
            node["size"] = len(data_bytes)
            if prefix in replacements:
                node["integrity"] = compute_integrity(data_bytes)

    rebuild_tree(header)
    pack_asar(header, bytes(new_payload), ASAR_PATH)
    print(f"Successfully patched and repacked {ASAR_PATH} ({os.path.getsize(ASAR_PATH)} bytes)")

    # Verify reading back from the repacked ASAR
    v_header, v_payload = read_asar(ASAR_PATH)
    v_preload = get_file_bytes(v_header, v_payload, "dist/preload.js").decode("utf-8")
    v_i18n = get_file_bytes(v_header, v_payload, "dist/i18n-ko.js").decode("utf-8")
    assert "i18n-ko" in v_preload and "__AGY_KO_VERSION__" in v_i18n
    print(f"Verified repacked ASAR: dist/preload.js ({len(v_preload)} chars), dist/i18n-ko.js ({len(v_i18n)} chars)")


def live_inject_cdp():
    import base64
    import socket
    import urllib.request

    port_file = os.path.expandvars(r"%APPDATA%\Antigravity\DevToolsActivePort")
    if not os.path.exists(port_file):
        print("DevToolsActivePort not found; skipping live CDP injection.")
        return

    with open(port_file, "r", encoding="utf-8") as f:
        port = int(f.readline().strip())

    with open(I18N_KO_JS_PATH, "r", encoding="utf-8") as f:
        script_source = f.read()

    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3).read().decode("utf-8"))
    page_targets = [t for t in targets if t.get("type") == "page" and "webSocketDebuggerUrl" in t]

    for t in page_targets:
        ws_url = t["webSocketDebuggerUrl"]
        # ws://127.0.0.1:PORT/devtools/page/ID
        path_part = "/" + ws_url.split("/", 3)[3]
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {path_part} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(1024)
        assert b"101 " in resp, f"Handshake failed: {resp}"

        def ws_send(obj):
            raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            mask = os.urandom(4)
            header_bytes = bytearray([0x81])
            n = len(raw)
            if n < 126:
                header_bytes.append(0x80 | n)
            elif n < 65536:
                header_bytes.append(0x80 | 126)
                header_bytes.extend(struct.pack(">H", n))
            else:
                header_bytes.append(0x80 | 127)
                header_bytes.extend(struct.pack(">Q", n))
            header_bytes.extend(mask)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(raw))
            sock.sendall(bytes(header_bytes) + masked)

        def ws_recv():
            b0, b1 = sock.recv(2)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", sock.recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", sock.recv(8))[0]
            buf = bytearray()
            while len(buf) < length:
                buf.extend(sock.recv(length - len(buf)))
            return json.loads(buf.decode("utf-8"))

        ws_send({"id": 1, "method": "Page.enable", "params": {}})
        ws_recv()
        ws_send({"id": 2, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": script_source}})
        ws_recv()
        ws_send({"id": 3, "method": "Runtime.evaluate", "params": {"expression": script_source, "returnByValue": True}})
        ws_recv()
        verify_expr = """
        JSON.stringify({
            version: window.__AGY_KO_VERSION__,
            sampleMenuTranslation: [
                { id: 'cmi-0', label: 'New Window', type: 'normal', checked: false, disabled: false, accelerator: 'Ctrl+Shift+N' },
                { id: 'cmi-1', label: 'Open Settings', type: 'normal', checked: false, disabled: false, accelerator: 'Ctrl+,' }
            ].map(x => x).map(x => x.label),
            topButtons: Array.from(document.querySelectorAll('button')).slice(0, 8).map(b => (b.innerText || b.getAttribute('aria-label') || '').trim()).filter(Boolean)
        })
        """
        ws_send({"id": 4, "method": "Runtime.evaluate", "params": {"expression": verify_expr, "returnByValue": True}})
        res = ws_recv()
        print("Live CDP injection verified:", res.get("result", {}).get("result", {}).get("value"))
        sock.close()


if __name__ == "__main__":
    patch_files()
    live_inject_cdp()
