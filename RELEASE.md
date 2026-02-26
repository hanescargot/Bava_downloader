# GitHub Releases 배포 가이드

## 1) 버전 올리기
- `VERSION` 파일을 수정합니다. 예: `1.0.4`
- `main.py`는 `VERSION` 파일 값을 자동으로 읽어 UI에 표시합니다.

## 2) 태그로 릴리즈 발행
- 태그 규칙은 `v<버전>` 입니다. 예: `v1.0.4`
- `VERSION` 값과 태그 버전이 다르면 GitHub Actions가 실패합니다.

```bash
git add VERSION
git commit -m "chore: release v1.0.4"
git tag v1.0.4
git push origin main
git push origin v1.0.4
```

## 3) 자동 빌드/업로드 결과
- 워크플로우: `.github/workflows/release.yml`
- 릴리즈 에셋:
  - `BaVa.Downloader-macos-universal2.zip` (Intel + Apple Silicon 공용)
  - `BaVa.Downloader-macos-universal2.zip.sha256`
  - `BaVa.Downloader-macos-arm64.zip` (Apple Silicon 전용)
  - `BaVa.Downloader-macos-arm64.zip.sha256`
  - `BaVa.Downloader-windows.zip`
  - `BaVa.Downloader-windows.zip.sha256`

## 4) 웹페이지에서 사용자 배포
- 앱 서버 환경변수에 저장소를 설정합니다.

```bash
export RELEASE_REPOSITORY="OWNER/REPO"
```

- 필요시 에셋명 변경:

```bash
export RELEASE_ASSET_NAME="BaVa.Downloader-macos-universal2.zip"
```

- 설정 후 웹페이지 헤더에 `최신 앱 다운로드` 버튼이 표시되고, 최신 GitHub Release 에셋 URL로 연결됩니다.
