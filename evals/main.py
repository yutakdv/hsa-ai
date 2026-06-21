"""eval 전체 파이프라인 통합 실행 진입점.

실행 방법:
    python evals/main.py

임계값 미달 시 exit code 1로 종료해 GitHub Actions merge 차단에 활용한다.

파이프라인:
    tasks.json 로드
    → runner.run_tasks()           : HTTP 호출 + 응답 수집
    → classify_runner.run_classification(): 분류 정확도용 in-process 예측 수집
    → grader.grade_results()       : 채점 + 임계값 계산
    → report.print_report()        : 콘솔 출력
    → sys.exit(0 or 1)
"""

import json
import sys
from pathlib import Path
from typing import Any

# evals/ 폴더를 경로에 추가해 runner, grader, report를 bare import할 수 있도록 한다.
sys.path.insert(0, str(Path(__file__).parent))
# 레포 루트를 경로에 추가해 classify_runner가 app.* 를 import할 수 있도록 한다.
# (CI는 `pip install -e .`로 app이 설치되지만, 로컬에서 직접 실행하면 미설치일 수 있다.)
sys.path.insert(0, str(Path(__file__).parent.parent))

import classify_runner
import grader
import report
import runner

TASKS_PATH = Path(__file__).parent / "tasks.json"


def load_tasks(path: Path) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] tasks.json not found: {path}")
        sys.exit(1)


def main() -> None:
    tasks = load_tasks(TASKS_PATH)
    results = runner.run_tasks(tasks)
    # category는 HTTP 응답에 노출되지 않으므로(Phase 0.3 ③) in-process 직접 호출로 분류 측정.
    predictions = classify_runner.run_classification(tasks)
    grade_report = grader.grade_results(results, predictions)
    passed = report.print_report(grade_report)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
