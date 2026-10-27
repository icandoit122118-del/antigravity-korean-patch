# Antigravity 데스크톱 전체 UI 한글 패치 (`antigravity-korean-patch`)

Google **Antigravity** PC 데스크톱 앱(`Antigravity.exe`)의 네이티브 메뉴, 트레이, 컨텍스트 메뉴, 대화창, 모델 및 사용량(주간·5시간 한도 및 잔여 시간 안내), 개발자 설정 등 전체 UI를 한글화하는 패치 패키지입니다.

## 구성 파일
- `ui-ko.json`: 1,071개 고정 UI 문자열 및 65개 동적 정규식 패턴 한국어 사전
- `i18n-ko.js`: 코드 블록·에디터·터미널(`.monaco-editor`, `.xterm`, `pre`, `code`)을 제외한 전체 DOM 텍스트·속성(`placeholder`, `title`, `aria-label`, `alt`) 및 네이티브 컨텍스트 메뉴(`showContextMenu`) 실시간 한글화 런타임
- `patcher.py`:
  1. 원본 `resources\app.asar`를 `resources\app.asar.bak`으로 자동 백업
  2. `app.asar` 내부의 Electron 메인·프리로드 스크립트(`dist/preload.js`, `dist/utils.js`, `dist/ipcHandlers.js`, `dist/main.js`, `dist/menu.js`, `dist/tray.js`, `dist/updater.js`, `dist/provisionSplash.js`, `dist/ideInstall/wizardHtml.js`) 영구 한글 패치 및 재패킹
  3. 현재 실행 중인 Antigravity 창이 있으면 재시작 없이 Chrome DevTools Protocol(`DevToolsActivePort`)을 통해 즉시 실시간 한글 패치 주입
- `apply-korean-patch.bat`: 원클릭 한글 패치 실행 배치 스크립트

## 사용 방법

```powershell
python patcher.py
```
또는 `apply-korean-patch.bat`을 더블클릭하여 실행합니다(Antigravity 앱 업데이트 후에도 다시 실행하면 즉시 재적용됩니다).
