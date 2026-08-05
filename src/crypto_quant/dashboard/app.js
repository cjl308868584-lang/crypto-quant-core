"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const overall = document.getElementById("overall-state");
  const summary = document.querySelector('[data-view="summary"]');
  const challenger = document.querySelector('[data-view="challenger"]');
  const paper = document.querySelector('[data-view="paper"]');
  const riskObservation = document.querySelector('[data-view="risk-observation"]');
  const alertList = document.querySelector('[data-view="alerts"]');

  const addFact = (target, label, value) => {
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value === null ? "—" : String(value);
    target.append(term, detail);
  };

  const render = (status) => {
    const projection = status.projection;
    const release = projection.release;
    const challenge = projection.challenger;
    const systemPaper = projection.system_paper;
    const alertSummary = status.alert_summary;

    overall.textContent = projection.status;
    overall.dataset.health = projection.status;

    summary.replaceChildren();
    addFact(summary, "版本", release.package_version);
    addFact(summary, "标签", release.release_tag);
    addFact(summary, "Main commit", release.main_commit);
    addFact(summary, "投影时间", projection.projected_at);
    addFact(summary, "身份", release.identity_status);

    challenger.replaceChildren();
    addFact(challenger, "阶段", challenge.phase);
    addFact(challenger, "服务", challenge.service_health);
    addFact(challenger, "证据", challenge.evidence_health);
    addFact(challenger, "已验证槽位", challenge.verified_slot_count);
    addFact(challenger, "已完成 Episode", challenge.completed_episode_count);
    addFact(challenger, "下一槽位", challenge.next_required_slot);
    addFact(challenger, "研究门", challenge.gate_status);

    paper.replaceChildren();
    addFact(paper, "阶段", systemPaper.phase);
    addFact(paper, "服务", systemPaper.service_health);
    addFact(paper, "证据", systemPaper.evidence_health);
    addFact(paper, "运行天数", systemPaper.elapsed_days);
    addFact(paper, "已验证槽位", systemPaper.verified_slot_count);
    addFact(paper, "已提交模拟订单", systemPaper.submitted_order_count);
    addFact(paper, "完全成交", systemPaper.filled_order_count);
    addFact(paper, "部分成交", systemPaper.partially_filled_order_count);
    addFact(paper, "取消", systemPaper.cancelled_order_count);
    addFact(paper, "拒绝", systemPaper.rejected_order_count);
    addFact(paper, "超时或未知", systemPaper.timeout_unknown_order_count);
    addFact(paper, "对账", systemPaper.reconciliation_status);
    addFact(paper, "风险", systemPaper.risk_state);
    addFact(paper, "最终门", systemPaper.gate_status);

    riskObservation.textContent = alertSummary.new_risk_allowed
      ? "观察状态：允许 System Paper 继续冻结范围内的模拟风险流程"
      : "观察状态：禁止新增模拟风险";
    alertList.replaceChildren();
    if (alertSummary.alerts.length === 0) {
      const empty = document.createElement("li");
      empty.textContent = "无活动告警";
      empty.className = "alert INFO";
      alertList.append(empty);
    } else {
      alertSummary.alerts.forEach((alert) => {
        const item = document.createElement("li");
        item.className = `alert ${alert.severity}`;
        item.textContent = `${alert.severity} · ${alert.stream} · ${alert.reason_code}`;
        alertList.append(item);
      });
    }
  };

  const failClosed = () => {
    overall.textContent = "FAILED_CLOSED · OPERATIONS_STATUS_UNAVAILABLE";
    overall.dataset.health = "FAILED_CLOSED";
    summary.replaceChildren();
    challenger.replaceChildren();
    paper.replaceChildren();
    alertList.replaceChildren();
    riskObservation.textContent = "观察状态：禁止新增模拟风险";
  };

  fetch("/api/v1/status", {cache: "no-store", credentials: "omit"})
    .then((response) => {
      if (!response.ok) {
        throw new Error("status unavailable");
      }
      return response.json();
    })
    .then(render)
    .catch(failClosed);
});
