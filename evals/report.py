"""GradeReport를 사람이 읽기 좋은 형태로 출력하는 report.

main.py에서 호출되며, 콘솔 출력만 담당한다.
임계값 통과 여부를 bool로 반환해 CI에서 sys.exit에 활용할 수 있도록 한다.
"""

from grader import GradeReport


def print_report(report: GradeReport) -> bool:
    """채점 결과를 출력하고, 모든 임계값을 통과했으면 True를 반환한다."""
    print("=" * 60)
    print(f"🚀 hsa-AI Quality Evaluation Suite  |  총 {report.total}개 케이스")
    print("=" * 60)

    # 케이스별 결과
    for case in report.cases:
        label = "✅ PASS" if case.passed else "❌ FAIL"
        print(f"\n[{case.task_id}] {label}  |  Latency: {case.latency}s")

        if case.runner_error:
            print(f"  ⚠️  Runner 오류: {case.runner_error}")
            print("-" * 60)
            continue

        if case.errors:
            print("  ⚠️  Detail Errors:")
            for err in case.errors:
                print(f"     - {err}")

        actual = case.actual or {}
        data = actual.get("data") or {}
        error_info = actual.get("error") or {}

        if data:
            draft = data.get("draftAnswer") or "N/A (Needs Review)"
            reason = data.get("reason", "No reason provided")
            print(f"  AI Response : {str(draft)[:60]}...")
            print(f"  Reason      : {reason}")
        elif error_info:
            print(f"  ⚠️  Server Error : {error_info.get('message', 'No message')}")
        else:
            print("  ⚠️  응답 데이터 없음")

        print("-" * 60)

    # 지표별 점수
    print("\n📊 지표별 점수")
    print("-" * 60)
    for m in report.metrics:
        if m.score is None:
            score_str = f"측정 불가 — {m.note}" if m.note else "측정 대상 없음"
            status = "❌" if not m.passed else "⏭️ "
        elif m.name == "p95 latency":
            score_str = f"{m.score:.2f}s  (임계값: < {m.threshold:.0f}s)"
            status = "✅" if m.passed else "❌"
        else:
            score_str = f"{m.score * 100:.1f}%  (임계값: {m.threshold * 100:.0f}%)"
            status = "✅" if m.passed else "❌"
        print(f"  {status}  {m.name:<20}  {score_str}")

    # 최종 요약
    print("\n" + "=" * 60)
    print("🏁 Evaluation Completed.")
    print(f"   PASS {report.pass_count} / FAIL {report.fail_count} / TOTAL {report.total}")

    if report.threshold_passed:
        print("   ✅ 모든 지표 통과, 실패 케이스 없음 — PR merge 가능")
    else:
        failed_metrics = [m.name for m in report.metrics if not m.passed]
        if failed_metrics:
            print(f"   ❌ 미통과 지표: {', '.join(failed_metrics)}")
        if report.fail_count > 0:
            print(
                f"   ❌ 실패 케이스 {report.fail_count}개 — "
                "AGENTS.md: 실패 태스크 1개라도 있으면 PR 금지"
            )
        print("   PR merge 차단 대상입니다.")

    print("=" * 60)

    return report.threshold_passed
