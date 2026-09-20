#!/bin/bash
# 전송된 툴이 실제로 import 되는지까지 확인한다.
# 문법 검사만으로는 부족하다 - _secretary_lib 가 없으면 파싱은 통과하고
# 로딩 시점에 실패하는데, 대화 앱은 그 실패를 조용히 넘길 수 있다.
TOOLS=/home/pollen/secretary/external_tools

echo "=== 파일 목록 ==="
find $TOOLS -type f | sort | sed 's|^|  |'

echo
echo "=== _secretary_lib ==="
if [ -d "$TOOLS/_secretary_lib" ]; then
  ls -la $TOOLS/_secretary_lib/ | sed 's/^/  /'
else
  echo "  없음"
fi

echo
echo "=== 앱 venv 파이썬(3.12)으로 실제 import 시험 ==="
cd $TOOLS
for m in ask_claude gmail_draft gmail_digest calendar_agenda calendar_add_event; do
  /venvs/apps_venv/bin/python - "$m" <<'PY' 2>&1 | sed 's/^/  /'
import sys, types, importlib
name = sys.argv[1]
# 대화 앱의 Tool 기반 클래스를 흉내내어, 우리 코드만 검사한다
core = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
class Tool: pass
class ToolDependencies: instance_path = None
core.Tool, core.ToolDependencies = Tool, ToolDependencies
sys.modules.update({
    "reachy_mini_conversation_app": types.ModuleType("a"),
    "reachy_mini_conversation_app.tools": types.ModuleType("b"),
    "reachy_mini_conversation_app.tools.core_tools": core,
})
sys.path.insert(0, ".")
try:
    mod = importlib.import_module(name)
    cls = next((v for v in vars(mod).values()
                if isinstance(v, type) and getattr(v, "name", None) == name), None)
    print(f"OK   {name:22} Tool.name={getattr(cls,'name',None)}")
except Exception as e:
    print(f"실패 {name:22} {type(e).__name__}: {e}")
PY
done

echo
echo "=== 인격 ==="
ls -la /home/pollen/secretary/profiles/secretary_ko/ | sed 's/^/  /'
