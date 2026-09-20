#!/bin/bash
# 관리자 화면을 systemd 서비스로 등록한다.
#
# 127.0.0.1 에만 바인딩한다. 이 화면에는 로그인이 없고 API 키가 들어 있으므로,
# 로봇 방화벽이 막아주기를 기대하는 대신 애초에 외부로 열지 않는다.
# 접근은 SSH 터널로만 한다 - 이미 인증된 경로 위에 얹는 것이 맞다.
set -e

echo "=== 1. 기존 프로세스 정리 ==="
pkill -f "admin/server.py" 2>/dev/null || true
sleep 1
echo "  완료"

echo
echo "=== 2. 서비스 파일 작성 ==="
sudo tee /etc/systemd/system/reachy-secretary-admin.service >/dev/null <<'UNIT'
[Unit]
Description=Reachy Secretary admin panel
After=network.target

[Service]
Type=simple
User=pollen
WorkingDirectory=/home/pollen/secretary
# 로그인이 없는 화면이고 API 키를 다룬다. 외부에 열지 않고 터널로만 접근한다.
Environment=REACHY_ADMIN_HOST=127.0.0.1
Environment=REACHY_ADMIN_PORT=8765
# 이 화면은 로봇 위에서 돈다. 데몬을 자기 IP 로 찾아 나가면 DHCP 가
# 주소를 바꿀 때 소리 조절이 조용히 죽는다.
Environment=REACHY_HOST=127.0.0.1
ExecStart=/home/pollen/secretary/.venv/bin/python /home/pollen/secretary/admin/server.py
Restart=always
RestartSec=5
# 4GB 기기다. 이 화면 하나가 로봇을 잡아먹는 일이 없도록 상한을 둔다.
MemoryMax=256M

[Install]
WantedBy=multi-user.target
UNIT
echo "  작성 완료"

echo
echo "=== 3. 서비스 등록 및 시작 ==="
sudo systemctl daemon-reload
sudo systemctl enable reachy-secretary-admin >/dev/null 2>&1
sudo systemctl restart reachy-secretary-admin
sleep 4
echo "  상태: $(systemctl is-active reachy-secretary-admin)"
echo "  부팅 시 자동시작: $(systemctl is-enabled reachy-secretary-admin)"

echo
echo "=== 4. 응답 확인 ==="
curl -s -m 5 -o /dev/null -w "  HTTP %{http_code}\n" http://127.0.0.1:8765/

echo
echo "=== 5. roles 항목 (업데이트 반영 여부) ==="
curl -s -m 5 http://127.0.0.1:8765/api/settings | python3 -c "
import sys, json
d = json.load(sys.stdin)
roles = d.get('roles')
if roles is None:
    print('  roles 없음 - 구버전입니다')
else:
    for r in roles:
        print(f\"  {r['label']}: {r['effective_label']} (지정: {r['assigned'] or '기본'})\")
" 2>/dev/null || echo "  조회 실패"

echo
echo "=== 완료 ==="
echo "  이제 재부팅해도 자동으로 뜹니다."
echo "  접근은 SSH 터널로:  ssh -N -L 8765:localhost:8765 pollen@192.168.45.147"
