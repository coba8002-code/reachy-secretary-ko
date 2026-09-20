#!/bin/bash
# 관리자 화면으로 가는 터널. 필요할 때 더블클릭해서 여세요.
clear
echo ''
echo '════════════════════════════════════════════'
echo '   관리자 화면 터널'
echo '════════════════════════════════════════════'
echo ''
echo '   비밀번호:  root'
echo ''
echo '   연결되면 조용히 멈춰 있습니다 (정상).'
echo '   이 창을 열어두세요.'
echo ''
echo '   브라우저:  http://localhost:8765'
echo '────────────────────────────────────────────'
echo ''
# 로봇 쪽 목적지를 127.0.0.1 로 못박는다. 'localhost' 로 두면 로봇에서
# ::1 로 먼저 해석되는데, 관리자 화면은 IPv4 에만 바인딩돼 있어 거부된다.
ssh -N -L 8765:127.0.0.1:8765 \
  -o ConnectTimeout=15 -o ConnectionAttempts=5 \
  -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  pollen@192.168.45.147
echo ''
echo '터널이 끊어졌습니다.'
read -p '엔터로 닫기...'
