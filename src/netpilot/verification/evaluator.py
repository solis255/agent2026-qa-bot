"""Overall objective verification, not resolution classification."""


class VerificationEvaluator:
    def evaluate(self, cycle):
        critical = [c for c in cycle.checks if c.importance == "critical"]
        comparable = [c for c in critical if c.change in {"improved","unchanged","worsened"}]
        if any(c.change == "worsened" for c in comparable):
            result = "worsened"
        elif any(c.change == "improved" for c in comparable):
            result = "improved"
        elif comparable and len(comparable) == len(critical):
            result = "unchanged"
        else:
            result = "inconclusive"
        reason = {"improved":"关键指标有改善，但不等于故障已解决。", "unchanged":"可比较关键指标无变化，验证流程已完成。", "worsened":"至少一个关键指标变差；请停止继续尝试并核对状态。", "inconclusive":"缺少足够的同目标、同指标有效修复后证据，暂时无法确认。"}[result]
        observation = cycle.user_observation.symptom_status if cycle.user_observation else "unknown"
        positive = observation in {"resolved_by_user_report","improved_by_user_report"}
        negative = observation in {"unchanged_by_user_report","worsened_by_user_report"}
        if positive and any(c.after_status == "abnormal" for c in critical):
            result,reason = "inconclusive","用户反馈与客观网络指标不一致：用户报告改善，但关键指标仍异常。"
        elif negative and result == "improved":
            result,reason = "inconclusive","网络指标改善，但用户症状没有改善；用户反馈与客观指标存在差异。"
        return result, reason
