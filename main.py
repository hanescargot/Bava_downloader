# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import yt_dlp
import os
import uuid
import re
import time
import json
import sys
import tempfile
import subprocess
from urllib.parse import urlparse
import logging
import requests

if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
CORS(app)  # 크로스 오리진 요청 허용

APP_NAME = 'BaVa Downloader'
DEFAULT_DOWNLOAD_DIR = '/tmp/downloads'
DEFAULT_APP_VERSION = '1.0.4'
VERSION_FILE = os.path.join(BASE_DIR, 'VERSION')
RELEASE_REPOSITORY = os.environ.get('RELEASE_REPOSITORY', os.environ.get('GITHUB_REPOSITORY', '')).strip()
RELEASE_ASSET_NAME = os.environ.get('RELEASE_ASSET_NAME', 'BaVa Downloader-macos.zip').strip()
RELEASE_CACHE_TTL_SECONDS = int(os.environ.get('RELEASE_CACHE_TTL_SECONDS', '600'))
PRIMARY_SETTINGS_FILE = os.path.join(
    os.path.expanduser('~'),
    'Library',
    'Application Support',
    'BaVaDownloader',
    'settings.json'
)
FALLBACK_SETTINGS_FILE = '/tmp/bava_downloader_settings.json'
SETTINGS_CANDIDATES = [PRIMARY_SETTINGS_FILE, FALLBACK_SETTINGS_FILE]

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_release_cache = {'fetched_at': 0.0, 'data': None}

def load_app_version():
    env_version = os.environ.get('APP_VERSION', '').strip()
    if env_version:
        return env_version
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, 'r', encoding='utf-8') as f:
                version = f.read().strip()
                if version:
                    return version
    except Exception as e:
        logger.warning(f"Failed to load version from {VERSION_FILE}: {e}")
    return DEFAULT_APP_VERSION

APP_VERSION = load_app_version()

def fetch_latest_release():
    if not RELEASE_REPOSITORY:
        return None

    api_url = f"https://api.github.com/repos/{RELEASE_REPOSITORY}/releases/latest"
    try:
        response = requests.get(
            api_url,
            headers={'Accept': 'application/vnd.github+json'},
            timeout=4,
        )
        if response.status_code != 200:
            logger.warning(f"GitHub release API returned status {response.status_code}")
            return None

        release = response.json()
        assets = release.get('assets') or []
        preferred_asset = next((asset for asset in assets if asset.get('name') == RELEASE_ASSET_NAME), None)
        zip_asset = next((asset for asset in assets if str(asset.get('name', '')).endswith('.zip')), None)
        selected_asset = preferred_asset or zip_asset

        return {
            'tag_name': release.get('tag_name'),
            'name': release.get('name'),
            'published_at': release.get('published_at'),
            'release_page_url': release.get('html_url'),
            'asset_name': selected_asset.get('name') if selected_asset else None,
            'asset_download_url': selected_asset.get('browser_download_url') if selected_asset else release.get('html_url'),
            'repository': RELEASE_REPOSITORY,
        }
    except Exception as e:
        logger.warning(f"Failed to fetch latest release from GitHub: {e}")
        return None

def get_release_info(force_refresh=False):
    now = time.time()
    if not force_refresh and _release_cache['data'] is not None and now - _release_cache['fetched_at'] < RELEASE_CACHE_TTL_SECONDS:
        return _release_cache['data']

    release_data = fetch_latest_release()
    if release_data is not None:
        _release_cache['data'] = release_data
        _release_cache['fetched_at'] = now
    return _release_cache['data']

def normalize_download_dir(path):
    if not path or not isinstance(path, str):
        return DEFAULT_DOWNLOAD_DIR
    normalized_path = os.path.abspath(os.path.expanduser(path.strip()))
    return normalized_path

def sanitize_filename(value):
    if not value or not isinstance(value, str):
        return 'video'
    sanitized = re.sub(r'[\\/:*?"<>|]+', '', value).strip()
    sanitized = re.sub(r'\s+', ' ', sanitized).strip('. ')
    return sanitized[:120] if sanitized else 'video'

def ensure_unique_filename(directory, base_name, ext_with_dot):
    candidate = f"{base_name}{ext_with_dot}"
    counter = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base_name} ({counter}){ext_with_dot}"
        counter += 1
    return candidate

def load_settings():
    settings = {'download_dir': DEFAULT_DOWNLOAD_DIR}
    for settings_file in SETTINGS_CANDIDATES:
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        settings.update(loaded)
                    break
        except Exception as e:
            logger.error(f"Failed to load settings from {settings_file}: {e}")

    settings['download_dir'] = normalize_download_dir(settings.get('download_dir'))
    return settings

def save_settings(settings):
    last_error = None
    for settings_file in SETTINGS_CANDIDATES:
        try:
            os.makedirs(os.path.dirname(settings_file), exist_ok=True)
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return
        except Exception as e:
            last_error = e
            logger.error(f"Failed to save settings to {settings_file}: {e}")
    if last_error:
        raise last_error

APP_SETTINGS = load_settings()

def get_download_dir():
    active_dir = normalize_download_dir(APP_SETTINGS.get('download_dir'))
    os.makedirs(active_dir, exist_ok=True)
    return active_dir

def can_write_to_directory(path):
    if not path or not os.path.isdir(path):
        return False
    if not os.access(path, os.W_OK | os.X_OK):
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix='.bava_write_test_', delete=True):
            pass
        return True
    except Exception:
        return False

def validate_download_dir(path):
    normalized_path = normalize_download_dir(path)
    if not os.path.isabs(normalized_path):
        return False, normalized_path, '절대 경로를 입력해주세요'
    if not os.path.exists(normalized_path) or not os.path.isdir(normalized_path):
        return False, normalized_path, '폴더 경로를 찾을 수 없습니다'
    if not can_write_to_directory(normalized_path):
        return False, normalized_path, '폴더 경로를 찾을 수 없습니다'
    return True, normalized_path, None

def discover_download_dirs():
    home_dir = os.path.expanduser('~')
    candidates = [
        APP_SETTINGS.get('download_dir'),
        os.path.join(home_dir, 'Downloads'),
        os.path.join(home_dir, 'Desktop'),
        os.path.join(home_dir, 'Documents'),
        DEFAULT_DOWNLOAD_DIR,
        home_dir,
    ]

    discovered = []
    seen = set()
    for candidate in candidates:
        normalized = normalize_download_dir(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if os.path.exists(normalized) and os.path.isdir(normalized) and can_write_to_directory(normalized):
            discovered.append(normalized)
    return discovered

def pick_folder_via_osascript():
    """
    Open macOS native folder picker without tkinter.
    Returns absolute folder path string, or None if canceled/unavailable.
    """
    script = (
        'var app = Application.currentApplication();'
        'app.includeStandardAdditions = true;'
        'app.chooseFolder().toString();'
    )
    try:
        result = subprocess.run(
            ['osascript', '-l', 'JavaScript', '-e', script],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"Folder picker launch failed: {e}")
        return None

    if result.returncode != 0:
        stderr = (result.stderr or '').strip()
        # -128: user canceled dialog
        if '-128' in stderr:
            logger.info('Folder picker canceled by user')
            return None
        logger.warning(f"Folder picker osascript error: {stderr}")
        return None

    selected = (result.stdout or '').strip()
    if not selected:
        return None

    normalized = normalize_download_dir(selected)
    if os.path.isdir(normalized) and can_write_to_directory(normalized):
        return normalized
    return None

def find_file_path(filename):
    search_dirs = [get_download_dir(), DEFAULT_DOWNLOAD_DIR]
    for directory in search_dirs:
        file_path = os.path.join(directory, filename)
        if os.path.exists(file_path):
            return file_path
    return None

os.makedirs(DEFAULT_DOWNLOAD_DIR, exist_ok=True)
get_download_dir()

# 파일을 주기적으로 정리하는 함수
def cleanup_old_files():
    current_time = time.time()
    try:
        # 사용자 지정 다운로드 경로는 보존하고, 임시 기본 경로만 정리
        for file in os.listdir(DEFAULT_DOWNLOAD_DIR):
            file_path = os.path.join(DEFAULT_DOWNLOAD_DIR, file)
            # 1시간(3600초) 이상 지난 파일 삭제
            if os.path.isfile(file_path) and current_time - os.path.getmtime(file_path) > 3600:
                try:
                    os.remove(file_path)
                    logger.info(f"Removed old file: {file}")
                except Exception as e:
                    logger.error(f"Error removing file {file}: {e}")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

# URL 유효성 검증
def is_valid_url(url, platform):
    parsed_url = urlparse(url)
    if platform == 'youtube':
        return bool(parsed_url.netloc in ['www.youtube.com', 'youtube.com', 'youtu.be'])
    elif platform == 'tiktok':
        return bool(parsed_url.netloc in ['www.tiktok.com', 'tiktok.com', 'vm.tiktok.com'])
    elif platform == 'instagram':
        return bool(parsed_url.netloc in ['www.instagram.com', 'instagram.com'])
    elif platform == 'facebook':
        return bool(parsed_url.netloc in ['www.facebook.com', 'facebook.com', 'fb.com', 'fb.watch', 'm.facebook.com'])
    return False

def clean_instagram_url(url):
    """인스타그램 URL을 정리하고 작동하는 형식으로 변환"""
    parsed_url = urlparse(url)
    path_parts = [p for p in parsed_url.path.split('/') if p]
    
    # ID 추출
    reel_id = None
    for i, part in enumerate(path_parts):
        if part == 'reel' and i+1 < len(path_parts):
            reel_id = path_parts[i+1]
            break
    
    if not reel_id and path_parts:
        # 마지막 경로 부분이 ID일 수 있음
        reel_id = path_parts[-1]
    
    if reel_id:
        # 작동하는 형식으로 변환 (쿼리 파라미터 제거)
        return f"https://www.instagram.com/reel/{reel_id}/"
    
    # 변환할 수 없는 경우 원래 경로 유지 (쿼리 제거)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

def clean_facebook_url(url):
    """페이스북 URL을 정리하고 작동하는 형식으로 변환"""
    parsed_url = urlparse(url)
    
    # fb.watch 형식 처리
    if parsed_url.netloc == 'fb.watch':
        # fb.watch는 단축 URL이므로 그대로 사용
        return url
    
    # 쿼리 파라미터에서 비디오 ID 추출 시도
    path = parsed_url.path
    
    # 일반적인 비디오 URL 패턴 (/watch/?v=...)
    if '/watch/' in path or '/watch' in path:
        return url  # 이미 적절한 형식
    
    # 비디오 경로가 포함된 URL (/videos/...)
    if '/videos/' in path:
        return url  # 이미 적절한 형식
    
    # 기타 페이스북 게시물의 경우 원본 URL 사용
    return url

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    data = request.json
    logger.info(f"Received video-info request: {data}")
    
    video_url = data.get('url')
    platform = data.get('platform', 'youtube')  # 기본값은 youtube
    
    if not video_url:
        return jsonify({'error': 'URL이 제공되지 않았습니다'}), 400
    
    if not is_valid_url(video_url, platform):
        return jsonify({'error': f'유효한 {platform} URL이 아닙니다'}), 400
    
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
        }
        
        # 플랫폼별 특화 옵션 추가
        if platform == 'instagram':
            video_url = clean_instagram_url(video_url)
            ydl_opts.update({
                'extract_flat': True,  # 플레이리스트 정보만 추출
            })
        elif platform == 'facebook':
            video_url = clean_facebook_url(video_url)
            ydl_opts.update({
                'extract_flat': False,  # 페이스북은 상세 정보 추출 필요
                'force_generic_extractor': False,  # 페이스북 전용 추출기 사용
            })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # 동영상 정보 추출
            video_data = {
                'id': info.get('id'),
                'title': info.get('title'),
                'duration': info.get('duration'),
                'upload_date': info.get('upload_date'),
                'thumbnail': info.get('thumbnail'),
                'suggested_filename': sanitize_filename(info.get('title')),
                'available_formats': []
            }
            
            # 사용 가능한 형식 정보
            for format in info.get('formats', []):
                if format.get('ext') in ['mp4', 'webm', 'mp3']:
                    video_data['available_formats'].append({
                        'format_id': format.get('format_id'),
                        'ext': format.get('ext'),
                        'resolution': format.get('resolution'),
                        'file_size': format.get('filesize')
                    })
            
            return jsonify({'success': True, 'data': video_data})
            
    except Exception as e:
        logger.error(f"Error extracting video info: {e}")
        return jsonify({'error': f'동영상 정보를 가져오는 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    data = request.json or {}
    logger.info(f"Received download request: {data}")
    
    video_url = data.get('url')
    format_code = data.get('format', 'best')  # 기본값 'best' 추가
    platform = data.get('platform', 'youtube')
    custom_filename = data.get('filename', '')
    
    if not video_url:
        return jsonify({'error': 'URL이 제공되지 않았습니다'}), 400
    
    if not is_valid_url(video_url, platform):
        return jsonify({'error': f'유효한 {platform} URL이 아닙니다'}), 400
    
    # 디렉토리 존재 여부 확인 및 로깅
    download_dir = get_download_dir()
    logger.info(f"Download directory exists: {os.path.exists(download_dir)}")
    
    # 임시 파일 ID 생성 (다운로드 완료 후 사용자 파일명으로 변경)
    file_id = str(uuid.uuid4())
    output_path = os.path.join(download_dir, f"{file_id}.%(ext)s")
    
    try:
        ydl_opts = {
            'format': format_code,
            'outtmpl': output_path,
            'restrictfilenames': True,
            'nocheckcertificate': True,  # 인증서 확인 건너뛰기
            'ignoreerrors': True,  # 일부 오류 무시
            'no_warnings': True,
            'quiet': True,
            # 사용자 에이전트 추가
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            }
        }
        
        # 오디오만 다운로드하는 경우 - FFmpeg 의존성 제거됨
        if format_code == 'mp3':
            ydl_opts.update({
                'format': 'bestaudio/best',
                # FFmpeg 의존성 사용하지 않음
            })
            
        # 플랫폼별 특화 옵션 추가
        if platform == 'instagram':
            video_url = clean_instagram_url(video_url)
            ydl_opts.update({
                'extract_flat': False,  # 실제 다운로드를 위해 상세 정보 추출
            })
        elif platform == 'facebook':
            video_url = clean_facebook_url(video_url)
            ydl_opts.update({
                'extract_flat': False,
                'force_generic_extractor': False,  # 페이스북 전용 추출기 사용
            })
        
        logger.info(f"Starting download for: {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("YoutubeDL initialized")
            info = ydl.extract_info(video_url, download=True)
            logger.info(f"Download completed, info: {info.get('title')}")
            
            # 잠시 기다려 파일 시스템 동기화
            time.sleep(1)
            
            # 다운로드 디렉토리 내용 확인
            logger.info(f"Files in directory: {os.listdir(download_dir)}")
            
            # 다운로드된 파일명 찾기
            filename = None
            for file in os.listdir(download_dir):
                if file.startswith(file_id):
                    filename = file
                    break
            
            if not filename:
                return jsonify({'error': '파일 다운로드 후 찾을 수 없습니다'}), 500
            
            temp_download_path = os.path.join(download_dir, filename)
            logger.info(f"Found downloaded file: {temp_download_path}")

            _, ext_with_dot = os.path.splitext(filename)
            base_name = sanitize_filename(custom_filename or info.get('title'))
            final_filename = ensure_unique_filename(download_dir, base_name, ext_with_dot)
            final_download_path = os.path.join(download_dir, final_filename)
            os.replace(temp_download_path, final_download_path)
            logger.info(f"Final downloaded file: {final_download_path}")
            
            # 파일 다운로드 URL 생성 (절대 URL 사용)
            app_url = request.url_root.rstrip('/')  # 애플리케이션의 기본 URL 가져오기
            download_url = f"{app_url}/api/files/{final_filename}"
            logger.info(f"Generated download URL: {download_url}")
            
            return jsonify({
                'success': True, 
                'download_url': download_url,
                'filename': final_filename,
                'title': info.get('title')
            })
            
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return jsonify({'error': f'동영상 다운로드 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/files/<filename>', methods=['GET'])
def serve_file(filename):
    file_path = find_file_path(filename)
    logger.info(f"Serving file: {file_path}")
    
    if not file_path or not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return jsonify({'error': '파일을 찾을 수 없습니다'}), 404
    
    # 파일명에서 확장자 추출
    _, ext = os.path.splitext(filename)
    ext = ext[1:]  # 점 제거
    
    # Content-Type 설정
    content_types = {
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        'mp3': 'audio/mpeg'
    }
    
    # 확장자에 맞는 Content-Type이 없을 경우 기본값 사용
    content_type = content_types.get(ext, 'application/octet-stream')
    
    download_name = os.path.basename(filename)
    logger.info(f"Sending file as: {download_name}, content-type: {content_type}")
    
    # 파일 제공 및 다운로드 설정
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype=content_type
    )

@app.route('/api/settings', methods=['GET'])
def get_settings():
    return jsonify({
        'success': True,
        'data': {
            'app_name': APP_NAME,
            'download_path': get_download_dir(),
            'default_download_path': DEFAULT_DOWNLOAD_DIR,
            'version': APP_VERSION,
            'release': get_release_info(),
        }
    })

@app.route('/api/release', methods=['GET'])
def get_release():
    release_data = get_release_info(force_refresh=True)
    if not release_data:
        return jsonify({'success': False, 'error': '릴리즈 정보를 찾을 수 없습니다'}), 404
    return jsonify({'success': True, 'data': release_data})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json or {}
    requested_path = data.get('download_path', '')
    previous_path = APP_SETTINGS.get('download_dir')

    if not requested_path:
        return jsonify({'error': '다운로드 경로를 입력해주세요'}), 400

    is_valid, normalized_path, validation_error = validate_download_dir(requested_path)
    if not is_valid:
        return jsonify({'error': validation_error}), 400

    try:
        APP_SETTINGS['download_dir'] = normalized_path
        save_settings(APP_SETTINGS)
        logger.info(f"Updated download directory: {normalized_path}")
        return jsonify({'success': True, 'download_path': normalized_path})
    except Exception as e:
        APP_SETTINGS['download_dir'] = previous_path or DEFAULT_DOWNLOAD_DIR
        logger.error(f"Failed to update settings: {e}")
        return jsonify({'error': f'경로 저장 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/api/validate-path', methods=['POST'])
def validate_path():
    data = request.json or {}
    requested_path = data.get('download_path', '')
    if not requested_path:
        return jsonify({'error': '다운로드 경로를 입력해주세요'}), 400

    is_valid, normalized_path, validation_error = validate_download_dir(requested_path)
    if not is_valid:
        return jsonify({'error': validation_error}), 400

    return jsonify({'success': True, 'download_path': normalized_path})

@app.route('/api/browse-folder', methods=['GET'])
def browse_folder():
    selected = pick_folder_via_osascript()
    if selected:
        return jsonify({'success': True, 'path': selected, 'source': 'dialog'})

    discovered = discover_download_dirs()
    if not discovered:
        return jsonify({'error': '폴더 경로를 찾을 수 없습니다'}), 404
    return jsonify({'success': True, 'path': discovered[0], 'candidates': discovered, 'source': 'fallback'})

@app.route('/')
def index():
    # 첫 번째 요청에서 정리 함수 실행
    cleanup_old_files()
    return render_template('index.html', app_version=APP_VERSION, app_name=APP_NAME, release_info=get_release_info())

if __name__ == '__main__':
    flask_host = os.environ.get('FLASK_HOST', '0.0.0.0')
    flask_port = int(os.environ.get('FLASK_PORT', '5252'))
    flask_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=flask_debug, host=flask_host, port=flask_port)
